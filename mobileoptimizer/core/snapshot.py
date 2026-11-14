"""Snapshots of prior state, saved before any change, with strict LIFO undo."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .actions import Action
from .adb import AdbDisconnected, AdbError
from .executors import revert

log = logging.getLogger(__name__)
PHONE_DIR = "/sdcard/MobileOptimizer"
# entries whose change may be on the phone: "attempted"/"failed" can have reached it even without a
# success reply, and reverting them is safe because revert is state-guarded or idempotent
REVERTABLE = frozenset({"applied", "applied_temporary", "attempted", "failed"})


@dataclass
class Entry:
    action: Action
    prior: object
    status: str = "pending"


@dataclass
class Snapshot:
    id: str
    serial: str
    created: str
    profile: str
    preset: str | None
    reverted: bool = False
    entries: list[Entry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"id": self.id, "serial": self.serial, "created": self.created, "profile": self.profile,
                "preset": self.preset, "reverted": self.reverted,
                "entries": [{"action": e.action.to_dict(), "prior": e.prior, "status": e.status}
                            for e in self.entries]}

    @classmethod
    def from_dict(cls, d: dict) -> "Snapshot":
        entries = [Entry(Action.from_dict(e["action"]), e["prior"], e["status"]) for e in d["entries"]]
        return cls(d["id"], d["serial"], d["created"], d["profile"], d.get("preset"),
                   d.get("reverted", False), entries)


def _safe_serial(serial: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in serial)


class SnapshotStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _dir(self, serial: str) -> Path:
        return self.root / _safe_serial(serial)

    def path(self, snap: Snapshot) -> Path:
        return self._dir(snap.serial) / f"{snap.id}.json"

    def new(self, serial: str, profile: str, preset: str | None) -> Snapshot:
        now = datetime.now(timezone.utc)
        snap_id = now.strftime("%Y%m%dT%H%M%S%fZ")
        existing = {s.id for s in self.list(serial)}
        while snap_id in existing:  # same microsecond: bump to keep ids unique and ordered
            now = now.replace(microsecond=(now.microsecond + 1) % 1_000_000)
            snap_id = now.strftime("%Y%m%dT%H%M%S%fZ")
        return Snapshot(snap_id, serial, now.isoformat(), profile, preset)

    def save(self, snap: Snapshot) -> None:
        d = self._dir(snap.serial)
        d.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(snap.to_dict(), f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path(snap))
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def list(self, serial: str) -> list[Snapshot]:
        d = self._dir(serial)
        if not d.exists():
            return []
        snaps = []
        for p in sorted(d.glob("*.json")):
            try:
                snaps.append(Snapshot.from_dict(json.loads(p.read_text(encoding="utf-8"))))
            except (OSError, ValueError, KeyError, TypeError) as e:
                log.warning("unreadable snapshot %s: %s", p, e)
        return snaps

    def load(self, serial: str, snap_id: str) -> Snapshot:
        p = self._dir(serial) / f"{snap_id}.json"
        return Snapshot.from_dict(json.loads(p.read_text(encoding="utf-8")))


def push_copy(adb, store: SnapshotStore, snap: Snapshot) -> None:
    try:
        adb.shell(["mkdir", "-p", PHONE_DIR])
        adb.push(store.path(snap), f"{PHONE_DIR}/{snap.id}.json")
    except AdbDisconnected:
        raise
    except (AdbError, OSError) as e:
        log.warning("could not copy snapshot to phone: %s", e)


def undo_chain(store: SnapshotStore, serial: str, snap_id: str) -> list[Snapshot]:
    snaps = [s for s in store.list(serial) if not s.reverted]
    ids = [s.id for s in snaps]
    if snap_id not in ids:
        return []
    return list(reversed(snaps[ids.index(snap_id):]))


def undo(adb, store: SnapshotStore, serial: str, snap_id: str) -> list[tuple[str, str | None]]:
    results = []
    for snap in undo_chain(store, serial, snap_id):
        for entry in reversed(snap.entries):
            if entry.status not in REVERTABLE:
                continue
            try:
                reason = revert(adb, entry.action, entry.prior)
            except AdbDisconnected:
                store.save(snap)
                raise
            except AdbError as e:
                reason = str(e)
            else:
                entry.status = "reverted"
            results.append((entry.action.id, reason))
        # stay live while anything is left, so the user can retry the undo
        snap.reverted = not any(e.status in REVERTABLE for e in snap.entries)
        store.save(snap)
    return results


def can_undo_single(store: SnapshotStore, serial: str, snap_id: str, action_id: str) -> bool:
    snaps = store.list(serial)
    ids = [s.id for s in snaps]
    if snap_id not in ids:
        return False
    snap = snaps[ids.index(snap_id)]
    if snap.reverted:
        return False
    entry = next((e for e in snap.entries if e.action.id == action_id), None)
    if entry is None or entry.status not in REVERTABLE:
        return False
    target = entry.action.target
    for later in snaps[ids.index(snap_id) + 1:]:
        if later.reverted:
            continue
        if any(e.action.target == target and e.status in REVERTABLE for e in later.entries):
            return False
    return True


def undo_single(adb, store: SnapshotStore, serial: str, snap_id: str, action_id: str) -> str | None:
    if not can_undo_single(store, serial, snap_id, action_id):
        return "sonraki bir oturum bu ayarı değiştirdi"
    snap = store.load(serial, snap_id)
    entry = next(e for e in snap.entries if e.action.id == action_id)
    try:
        reason = revert(adb, entry.action, entry.prior)
    except AdbDisconnected:
        raise
    except AdbError as e:
        return str(e)  # entry stays revertable
    entry.status = "reverted"
    snap.reverted = not any(e.status in REVERTABLE for e in snap.entries)
    store.save(snap)
    return reason
