from mobileoptimizer.core.actions import Action
from mobileoptimizer.core.executors import apply, capture
from mobileoptimizer.core.snapshot import (Entry, SnapshotStore, can_undo_single, push_copy,
                                           undo, undo_chain, undo_single)
from tests.fakes import FakeAdb

PKG = "com.facebook.appmanager"


def S(aid, key, value):
    return Action(id=aid, type="setting", title="t", description="d", category="performance",
                  risk="safe", params={"namespace": "global", "key": key, "value": value}, verified=True)


ANIM = S("anim", "window_animation_scale", "0.5")
TRANS = S("trans", "transition_animation_scale", "0.5")
DIS = Action(id="dis", type="package_disable", title="t", description="d", category="cleanup",
             risk="safe", params={"package": PKG}, verified=True)


def fake():
    fa = FakeAdb("S1")
    fa.settings[("global", "window_animation_scale")] = "1.0"
    fa.settings[("global", "transition_animation_scale")] = "1.0"
    fa.packages = {PKG: "enabled"}
    fa.system_image = {PKG}
    return fa


def run(fa, store, actions, statuses=None):
    snap = store.new("S1", "generic", "balanced")
    for i, a in enumerate(actions):
        status = (statuses or {}).get(a.id, "applied")
        snap.entries.append(Entry(a, capture(fa, a), status))
        if status == "applied":
            apply(fa, a)
    store.save(snap)
    return snap


def test_save_load_roundtrip(tmp_path):
    fa, store = fake(), SnapshotStore(tmp_path)
    snap = run(fa, store, [ANIM, DIS])
    got = store.load("S1", snap.id)
    assert got == snap
    assert [s.id for s in store.list("S1")] == [snap.id]


def test_save_leaves_no_tmp_file(tmp_path):
    store = SnapshotStore(tmp_path)
    run(fake(), store, [ANIM])
    assert [p.suffix for p in (tmp_path / "S1").iterdir()] == [".json"]


def test_undo_chain_lifo(tmp_path):
    fa, store = fake(), SnapshotStore(tmp_path)
    s1, s2, s3 = (run(fa, store, [ANIM]) for _ in range(3))
    assert [s.id for s in undo_chain(store, "S1", s1.id)] == [s3.id, s2.id, s1.id]
    assert [s.id for s in undo_chain(store, "S1", s3.id)] == [s3.id]


def test_double_apply_full_undo(tmp_path):
    fa, store = fake(), SnapshotStore(tmp_path)
    s1 = run(fa, store, [ANIM])
    run(fa, store, [ANIM])
    undo(fa, store, "S1", s1.id)
    assert fa.settings[("global", "window_animation_scale")] == "1.0"
    assert all(s.reverted for s in store.list("S1"))
    assert undo_chain(store, "S1", s1.id) == []


def test_undo_package_and_setting(tmp_path):
    fa, store = fake(), SnapshotStore(tmp_path)
    s1 = run(fa, store, [ANIM, DIS])
    assert fa.packages[PKG] == "disabled"
    assert undo(fa, store, "S1", s1.id) == [("dis", None), ("anim", None)]
    assert fa.packages[PKG] == "enabled"
    assert fa.settings[("global", "window_animation_scale")] == "1.0"


def test_can_undo_single_blocked_by_later_snapshot(tmp_path):
    fa, store = fake(), SnapshotStore(tmp_path)
    s1 = run(fa, store, [ANIM, TRANS])
    run(fa, store, [ANIM])
    assert not can_undo_single(store, "S1", s1.id, "anim")
    assert can_undo_single(store, "S1", s1.id, "trans")
    assert undo_single(fa, store, "S1", s1.id, "trans") is None
    assert fa.settings[("global", "transition_animation_scale")] == "1.0"
    assert store.load("S1", s1.id).entries[1].status == "reverted"


def test_undo_skips_failed_and_not_run_entries(tmp_path):
    fa, store = fake(), SnapshotStore(tmp_path)
    s1 = run(fa, store, [ANIM, TRANS], {"trans": "not_run"})
    fa.settings[("global", "transition_animation_scale")] = "0.7"
    undo(fa, store, "S1", s1.id)
    assert fa.settings[("global", "transition_animation_scale")] == "0.7"
    assert fa.settings[("global", "window_animation_scale")] == "1.0"


def test_undo_reports_gone_package_reason(tmp_path):
    fa, store = fake(), SnapshotStore(tmp_path)
    s1 = run(fa, store, [DIS])
    del fa.packages[PKG]
    fa.system_image.clear()
    result = undo(fa, store, "S1", s1.id)
    assert result[0][0] == "dis" and result[0][1]


def test_push_copy_writes_to_phone(tmp_path):
    fa, store = fake(), SnapshotStore(tmp_path)
    snap = run(fa, store, [ANIM])
    push_copy(fa, store, snap)
    assert f"/sdcard/MobileOptimizer/{snap.id}.json" in fa.pushed


def test_push_copy_failure_does_not_raise(tmp_path):
    fa, store = fake(), SnapshotStore(tmp_path)
    snap = run(fa, store, [ANIM])
    fa.fail_push = True
    push_copy(fa, store, snap)
