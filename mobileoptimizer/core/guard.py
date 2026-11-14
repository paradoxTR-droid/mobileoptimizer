"""Third blacklist layer: packages this specific phone relies on (dialer, SMS, home, keyboard)."""

from __future__ import annotations

from .adb import AdbDisconnected, AdbError
from .blacklist import CORE_BLACKLIST

_ROLES = ("android.app.role.DIALER", "android.app.role.SMS", "android.app.role.HOME")


def _pkg(component: str) -> str:
    return component.strip().split("/", 1)[0].strip()


def _safe(adb, args):
    try:
        r = adb.shell(args)
    except AdbDisconnected:
        raise
    except AdbError:
        return ""
    return r.out if r.code == 0 else ""


def device_critical_packages(adb) -> frozenset[str]:
    found: set[str] = set()
    for role in _ROLES:
        for line in _safe(adb, ["cmd", "role", "get-role-holders", role]).splitlines():
            found.add(_pkg(line))
    ime = _safe(adb, ["settings", "get", "secure", "default_input_method"]).strip()
    if ime and ime != "null":
        found.add(_pkg(ime))
    lines = _safe(adb, ["cmd", "package", "resolve-activity", "--brief", "-a",
                        "android.intent.action.MAIN", "-c", "android.intent.category.HOME"]).splitlines()
    if lines and "/" in lines[-1]:
        found.add(_pkg(lines[-1]))
    return frozenset(p for p in found if p)


def blocked_set(adb, profile) -> frozenset[str]:
    return CORE_BLACKLIST | profile.blacklist_add | device_critical_packages(adb)
