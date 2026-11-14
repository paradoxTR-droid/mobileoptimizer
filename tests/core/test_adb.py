import sys
from pathlib import Path

import pytest

from mobileoptimizer.core.adb import Adb, AdbDisconnected, DeviceEntry, find_adb
from tests.fakes import FakeAdb


def test_devices_parses_states(fake_run):
    fake_run.stdout = "List of devices attached\r\nR5CX1\tdevice\r\nabc\tunauthorized\r\n\r\n"
    assert Adb(Path("adb")).devices() == [DeviceEntry("R5CX1", "device"), DeviceEntry("abc", "unauthorized")]


def test_shell_quotes_args_and_strips_cr(fake_run):
    fake_run.stdout = "0.5\r\n"
    r = Adb(Path("adb"), "R5CX1").shell(["settings", "get", "global", "window_animation_scale"])
    assert r.out == "0.5\n"
    assert fake_run.last_args == ["adb", "-s", "R5CX1", "shell", "settings get global window_animation_scale"]


def test_shell_quotes_dangerous_arg(fake_run):
    Adb(Path("adb"), "R5CX1").shell(["echo", "a; reboot"])
    assert fake_run.last_args[-1] == "echo 'a; reboot'"


def test_shell_raises_disconnected(fake_run):
    fake_run.returncode, fake_run.stderr = 1, "error: device 'R5CX1' not found"
    with pytest.raises(AdbDisconnected):
        Adb(Path("adb"), "R5CX1").shell(["true"])


def test_find_adb_prefers_vendor_dir(tmp_path, monkeypatch):
    exe = tmp_path / "vendor/adb/linux/adb"
    exe.parent.mkdir(parents=True)
    exe.touch()
    monkeypatch.setattr(sys, "platform", "linux")
    assert find_adb(tmp_path) == exe


def test_fake_adb_disconnect_after():
    fa = FakeAdb()
    fa.disconnect_after = 0
    with pytest.raises(AdbDisconnected):
        fa.shell(["settings", "get", "global", "x"])
