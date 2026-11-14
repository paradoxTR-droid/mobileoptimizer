"""Thin wrapper around the adb executable."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


class AdbError(Exception):
    pass


class AdbDisconnected(AdbError):
    pass


@dataclass(frozen=True)
class ShellResult:
    code: int
    out: str
    err: str


@dataclass(frozen=True)
class DeviceEntry:
    serial: str
    state: str


_DISCONNECT_MARKERS = ("not found", "offline", "no devices")


class Adb:
    def __init__(self, adb_path: Path, serial: str | None = None):
        self.adb_path = Path(adb_path)
        self.serial = serial

    def _run(self, args: list[str], timeout: int = 120) -> ShellResult:
        cmd = [str(self.adb_path)]
        if self.serial:
            cmd += ["-s", self.serial]
        cmd += args
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout, **kwargs)
        except FileNotFoundError as e:
            raise AdbError(f"adb çalıştırılamadı: {e}") from e
        except subprocess.TimeoutExpired as e:
            raise AdbError("adb zaman aşımı") from e
        out = (p.stdout or "").replace("\r", "")
        err = (p.stderr or "").replace("\r", "")
        if p.returncode != 0 and any(m in err for m in _DISCONNECT_MARKERS):
            raise AdbDisconnected(err.strip())
        return ShellResult(p.returncode, out, err)

    def devices(self) -> list[DeviceEntry]:
        r = Adb(self.adb_path)._run(["devices"])
        entries = []
        for line in r.out.splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) == 2:
                entries.append(DeviceEntry(parts[0].strip(), parts[1].strip()))
        return entries

    def shell(self, args: list[str], timeout: int = 120) -> ShellResult:
        return self._run(["shell", shlex.join(args)], timeout=timeout)

    def push(self, local: Path, remote: str) -> None:
        r = self._run(["push", str(local), remote])
        if r.code != 0:
            raise AdbError(r.err.strip() or r.out.strip())


def find_adb(base: Path | None = None) -> Path:
    if base is None:
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    plat, exe = ("windows", "adb.exe") if sys.platform == "win32" else ("linux", "adb")
    vendored = Path(base) / "vendor" / "adb" / plat / exe
    if vendored.exists():
        return vendored
    found = shutil.which("adb")
    if found:
        return Path(found)
    raise AdbError("adb bulunamadı")
