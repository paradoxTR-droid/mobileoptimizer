"""In-memory stand-in for Adb. Command handlers are added per task."""

from __future__ import annotations

from pathlib import Path

from mobileoptimizer.core.adb import AdbDisconnected, DeviceEntry, ShellResult


class FakeAdb:
    def __init__(self, serial: str = "FAKE1"):
        self.serial = serial
        self.device_list: list[DeviceEntry] = [DeviceEntry(serial, "device")]
        self.props: dict[str, str] = {}
        self.settings: dict[tuple[str, str], str] = {}
        self.packages: dict[str, str] = {}
        self.system_image: set[str] = set()
        self.appops: dict[tuple[str, str], str] = {}
        self.buckets: dict[str, int] = {}
        self.device_config: dict[tuple[str, str], str] = {}
        self.roles: dict[str, str] = {}
        self.ime: str = ""
        self.home: str = ""
        self.pushed: dict[str, str] = {}
        self.calls: list[list[str]] = []
        self.disconnect_after: int | None = None
        self.fail_push = False

    # --- public Adb surface -------------------------------------------------
    def devices(self) -> list[DeviceEntry]:
        return list(self.device_list)

    def shell(self, args: list[str]) -> ShellResult:
        if self.disconnect_after is not None and len(self.calls) >= self.disconnect_after:
            raise AdbDisconnected("device offline")
        self.calls.append(list(args))
        handler = getattr(self, "_h_" + args[0].replace("-", "_"), None)
        if handler is None:
            raise AssertionError(f"FakeAdb: unhandled command {args}")
        return handler(args[1:])

    def push(self, local: Path, remote: str) -> None:
        if self.disconnect_after is not None and len(self.calls) >= self.disconnect_after:
            raise AdbDisconnected("device offline")
        if self.fail_push:
            from mobileoptimizer.core.adb import AdbError
            raise AdbError("push failed")
        self.pushed[remote] = Path(local).read_text(encoding="utf-8")

    # --- helpers --------------------------------------------------------------
    @staticmethod
    def ok(out: str = "") -> ShellResult:
        return ShellResult(0, out, "")

    @staticmethod
    def fail(err: str = "error", code: int = 1) -> ShellResult:
        return ShellResult(code, "", err)
