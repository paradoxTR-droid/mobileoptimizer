"""Preview -> snapshot -> apply -> report, plus drift detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from .actions import Action
from .adb import AdbDisconnected, AdbError
from .executors import apply, capture, is_applicable, verify
from .snapshot import Entry, Snapshot, SnapshotStore, push_copy

TEMP_DETAIL = "uygulandı (zamanla sıfırlanabilir)"
DISCONNECTED = "bağlantı koptu"


@dataclass
class Preview:
    to_apply: list[Action] = field(default_factory=list)
    skipped: list[tuple[Action, str]] = field(default_factory=list)


@dataclass
class Result:
    action_id: str
    status: str
    detail: str = ""


def _skip_reason(adb, a: Action, info, blocked: frozenset[str]) -> str | None:
    if (a.min_sdk and info.sdk < a.min_sdk) or (a.max_sdk and info.sdk > a.max_sdk):
        return "Android sürümü uygun değil"
    if a.rom and info.rom not in a.rom:
        return "bu arayüzde yok"
    if info.sdk < 29 and (a.origin != "generic" or a.risk != "safe"):
        return "Android sürümü desteklenmiyor"
    if a.package and a.package in blocked:
        return "korumalı paket"
    return is_applicable(adb, a)


def build_preview(adb, profile, info, blocked: frozenset[str], *, preset: str | None = None,
                  action_ids: Iterable[str] = ()) -> Preview:
    ids = list(profile.presets[preset]) if preset else list(action_ids)
    pv = Preview()
    for aid in ids:
        a = profile.actions[aid]
        reason = _skip_reason(adb, a, info, blocked)
        if reason:
            pv.skipped.append((a, reason))
        else:
            pv.to_apply.append(a)
    return pv


def _apply_one(adb, store: SnapshotStore, snap: Snapshot, e: Entry) -> Result:
    a = e.action
    e.status = "attempted"  # if we crash or lose the reply, undo still reverts this one
    store.save(snap)
    try:
        apply(adb, a)
    except AdbDisconnected:
        raise
    except AdbError as err:
        e.status = "failed"
        return Result(a.id, "failed", str(err))
    e.status = "applied_temporary" if a.temporary else "applied"
    store.save(snap)
    try:
        ok = verify(adb, a)
    except AdbError:  # includes AdbDisconnected: the next apply will notice the cable
        return Result(a.id, "failed", "uygulandı, doğrulama yapılamadı")
    if not ok:
        return Result(a.id, "failed", "uygulandı ama doğrulanamadı")
    return Result(a.id, e.status, TEMP_DETAIL if a.temporary else "uygulandı")


def run(adb, preview: Preview, store: SnapshotStore, serial: str, profile_name: str, preset: str | None,
        on_progress: Callable[[int, int, Action], None] = lambda *a: None) -> tuple[Snapshot, list[Result]]:
    snap = store.new(serial, profile_name, preset)
    cut = False
    capture_errors: dict[str, str] = {}
    for a in preview.to_apply:
        if not cut:
            try:
                snap.entries.append(Entry(a, capture(adb, a), "pending"))
                continue
            except AdbDisconnected:
                cut = True
            except AdbError as err:  # no prior recorded: never apply this one
                capture_errors[a.id] = str(err)
        snap.entries.append(Entry(a, None, "not_run"))
    if cut:  # never apply anything whose prior state we could not record
        for e in snap.entries:
            e.status = "not_run"
    store.save(snap)
    if not cut:
        try:
            push_copy(adb, store, snap)
        except AdbDisconnected:
            cut = True

    results: list[Result] = []
    total = len(snap.entries)
    for i, e in enumerate(snap.entries, 1):
        if e.action.id in capture_errors:
            results.append(Result(e.action.id, "not_run", capture_errors[e.action.id]))
            continue
        if cut:
            if e.status == "pending":
                e.status = "not_run"
            results.append(Result(e.action.id, "not_run", DISCONNECTED))
            continue
        on_progress(i, total, e.action)
        try:
            results.append(_apply_one(adb, store, snap, e))
        except AdbDisconnected:
            cut = True  # entry stays "attempted": the phone may have run it
            results.append(Result(e.action.id, "not_run", DISCONNECTED))
        store.save(snap)
    store.save(snap)
    results += [Result(a.id, "skipped", r) for a, r in preview.skipped]
    return snap, results


def check_drift(adb, store: SnapshotStore, serial: str) -> list[str]:
    live = [s for s in store.list(serial) if not s.reverted]
    if not live:
        return []
    return [e.action.id for e in live[-1].entries
            if e.status in ("applied", "applied_temporary") and not verify(adb, e.action)]
