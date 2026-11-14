import json

from mobileoptimizer.core.actions import Action
from mobileoptimizer.core.device import DeviceInfo
from mobileoptimizer.core.profiles import Profile
from mobileoptimizer.core.session import build_preview, check_drift, run
from mobileoptimizer.core.snapshot import SnapshotStore, undo
from tests.fakes import FakeAdb

PKG = "com.facebook.appmanager"


def mk(aid, type_="setting", origin="generic", risk="safe", **kw):
    params = kw.pop("params", None)
    if params is None:
        params = {"namespace": "global", "key": aid, "value": "0.5"} if type_ == "setting" else {"package": PKG}
    return Action(id=aid, type=type_, title=aid, description="d", category="performance", risk=risk,
                  params=params, verified=True, origin=origin, **kw)


def profile(*actions, presets=None):
    return Profile("samsung", "samsung", ("samsung",), {a.id: a for a in actions},
                   presets or {"balanced": tuple(a.id for a in actions)}, frozenset())


def info(sdk=34, rom="oneui"):
    return DeviceInfo("S1", "samsung", "samsung", "A25", "14", sdk, rom, "6.1")


def fake():
    fa = FakeAdb("S1")
    for k in ("a", "b", "c", "old", "brand_only"):
        fa.settings[("global", k)] = "1.0"
    fa.packages = {PKG: "enabled"}
    fa.system_image = {PKG}
    return fa


def test_preview_filters_sdk_rom_blocked():
    fa = fake()
    p = profile(mk("a"), mk("b", min_sdk=35), mk("c", rom=("hyperos",)), mk("dis", "package_disable"))
    pv = build_preview(fa, p, info(), frozenset({PKG}), preset="balanced")
    assert [a.id for a in pv.to_apply] == ["a"]
    reasons = {a.id: r for a, r in pv.skipped}
    assert reasons == {"b": "Android sürümü uygun değil", "c": "bu arayüzde yok", "dis": "korumalı paket"}


def test_old_android_only_generic_safe():
    p = profile(mk("old"), mk("brand_only", origin="samsung"), mk("b", risk="careful"))
    pv = build_preview(fake(), p, info(sdk=28), frozenset(), action_ids=["old", "brand_only", "b"])
    assert [a.id for a in pv.to_apply] == ["old"]
    assert {a.id for a, r in pv.skipped if r == "Android sürümü desteklenmiyor"} == {"brand_only", "b"}


def test_missing_package_skipped(tmp_path):
    fa = fake()
    p = profile(mk("gone", "package_disable", params={"package": "com.not.here"}))
    pv = build_preview(fa, p, info(), frozenset(), preset="balanced")
    assert pv.to_apply == [] and pv.skipped[0][1] == "cihazda yok"
    snap, results = run(fa, pv, SnapshotStore(tmp_path), "S1", "samsung", "balanced")
    assert [(r.action_id, r.status) for r in results] == [("gone", "skipped")]
    assert snap.entries == []


def test_snapshot_saved_before_first_apply(tmp_path):
    fa = fake()
    store = SnapshotStore(tmp_path)
    pv = build_preview(fa, profile(mk("a"), mk("b")), info(), frozenset(), preset="balanced")
    seen = {}
    orig = fa._h_settings

    def spy(a):
        if a[0] == "put" and "file" not in seen:
            files = list((tmp_path / "S1").glob("*.json"))
            seen["file"] = json.loads(files[0].read_text())["entries"] if files else None
        return orig(a)

    fa._h_settings = spy
    run(fa, pv, store, "S1", "samsung", "balanced")
    assert seen["file"] is not None
    assert [e["prior"] for e in seen["file"]] == ["1.0", "1.0"]


def test_disconnect_mid_run(tmp_path):
    fa = fake()
    store = SnapshotStore(tmp_path)
    pv = build_preview(fa, profile(mk("a"), mk("b"), mk("c")), info(), frozenset(), preset="balanced")
    start = len(fa.calls)
    # 3 captures + mkdir + (put, verify-get) for the first action, then the cable goes
    fa.disconnect_after = start + 3 + 1 + 2
    snap, results = run(fa, pv, store, "S1", "samsung", "balanced")
    assert [(r.action_id, r.status) for r in results] == [("a", "applied"), ("b", "not_run"), ("c", "not_run")]
    # "b" was being sent when the cable went: it may have reached the phone, so it stays revertable
    assert [e.status for e in store.load("S1", snap.id).entries] == ["applied", "attempted", "not_run"]
    fa.disconnect_after = None
    undo(fa, store, "S1", snap.id)
    assert fa.settings[("global", "a")] == "1.0"


def test_failure_continues(tmp_path):
    fa = fake()
    p = profile(mk("dis", "package_disable"), mk("a"))
    pv = build_preview(fa, p, info(), frozenset(), preset="balanced")
    fa.pm_failure = "Failure [boom]"
    _, results = run(fa, pv, SnapshotStore(tmp_path), "S1", "samsung", "balanced")
    assert [(r.action_id, r.status) for r in results] == [("dis", "failed"), ("a", "applied")]
    assert "boom" in results[0].detail


def test_temporary_status(tmp_path):
    fa = fake()
    p = profile(mk("bk", "standby_bucket", params={"package": PKG, "bucket": "rare"}))
    pv = build_preview(fa, p, info(), frozenset(), preset="balanced")
    _, results = run(fa, pv, SnapshotStore(tmp_path), "S1", "samsung", "balanced")
    assert results[0].status == "applied_temporary"
    assert results[0].detail == "uygulandı (zamanla sıfırlanabilir)"


def test_progress_callback(tmp_path):
    fa = fake()
    pv = build_preview(fa, profile(mk("a"), mk("b")), info(), frozenset(), preset="balanced")
    seen = []
    run(fa, pv, SnapshotStore(tmp_path), "S1", "samsung", "balanced", lambda i, n, a: seen.append((i, n, a.id)))
    assert seen == [(1, 2, "a"), (2, 2, "b")]


def test_check_drift_detects_bucket_change(tmp_path):
    fa = fake()
    store = SnapshotStore(tmp_path)
    p = profile(mk("bk", "standby_bucket", params={"package": PKG, "bucket": "rare"}), mk("a"))
    run(fa, build_preview(fa, p, info(), frozenset(), preset="balanced"), store, "S1", "samsung", "balanced")
    assert check_drift(fa, store, "S1") == []
    fa.buckets[PKG] = 10
    assert check_drift(fa, store, "S1") == ["bk"]


def test_disconnect_during_apply_reply_keeps_entry_revertable(tmp_path):
    fa = fake()
    store = SnapshotStore(tmp_path)
    pv = build_preview(fa, profile(mk("a"), mk("b")), info(), frozenset(), preset="balanced")
    orig = fa._h_settings

    def put_then_drop(a):
        r = orig(a)
        if a[0] == "put":
            from mobileoptimizer.core.adb import AdbDisconnected
            raise AdbDisconnected("device offline")  # phone ran it, reply lost
        return r

    fa._h_settings = put_then_drop
    snap, results = run(fa, pv, store, "S1", "samsung", "balanced")
    assert results[0].status == "not_run"
    assert fa.settings[("global", "a")] == "0.5"
    fa._h_settings = orig
    undo(fa, store, "S1", snap.id)
    assert fa.settings[("global", "a")] == "1.0"


def test_timeout_in_verify_does_not_escape_run(tmp_path):
    fa = fake()
    pv = build_preview(fa, profile(mk("a"), mk("b")), info(), frozenset(), preset="balanced")
    orig = fa._h_settings
    calls = {"get": 0}

    def slow_get(a):
        if a[0] == "get" and a[2] == "a":
            calls["get"] += 1
            if calls["get"] == 2:  # 1st get is capture, 2nd is verify
                from mobileoptimizer.core.adb import AdbError
                raise AdbError("adb zaman aşımı")
        return orig(a)

    fa._h_settings = slow_get
    snap, results = run(fa, pv, SnapshotStore(tmp_path), "S1", "samsung", "balanced")
    assert [(r.action_id, r.status) for r in results] == [("a", "failed"), ("b", "applied")]
    assert snap.entries[0].status == "applied"


def test_capture_error_skips_only_that_action(tmp_path):
    fa = fake()
    pv = build_preview(fa, profile(mk("a"), mk("b")), info(), frozenset(), preset="balanced")
    orig = fa._h_settings

    def bad_capture(a):
        if a[0] == "get" and a[2] == "a":
            from mobileoptimizer.core.adb import AdbError
            raise AdbError("adb zaman aşımı")
        return orig(a)

    fa._h_settings = bad_capture
    snap, results = run(fa, pv, SnapshotStore(tmp_path), "S1", "samsung", "balanced")
    assert [(r.action_id, r.status) for r in results] == [("a", "not_run"), ("b", "applied")]
    assert fa.settings[("global", "a")] == "1.0"
