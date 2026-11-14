"""Per-type capture / apply / verify / revert for actions."""

from __future__ import annotations

from .actions import Action
from .adb import AdbError

_BUCKET_NAMES = {5: "active", 10: "active", 20: "working_set", 30: "frequent", 40: "rare", 45: "restricted"}
_FAIL_MARKERS = ("Failure", "Exception", "Error:", "doesn't exist", "Unknown package")

REASON_MISSING = "cihazda yok"
REASON_ALREADY_REMOVED = "zaten kaldırılmış"
REASON_GONE = "cihazda artık yok"


def _run(adb, args: list[str]) -> str:
    r = adb.shell(args)
    if r.code != 0 or any(m in r.out for m in _FAIL_MARKERS):
        raise AdbError(f"{' '.join(args)}: {(r.err or r.out).strip()}")
    return r.out


def _get(adb, args: list[str]) -> str | None:
    out = adb.shell(args).out.strip()
    return None if out in ("", "null") else out


def _list(adb, flag: str | None = None) -> set[str]:
    args = ["pm", "list", "packages"] + ([flag] if flag else [])
    return {line[len("package:"):].strip() for line in adb.shell(args).out.splitlines()
            if line.startswith("package:")}


def package_state(adb, pkg: str) -> str | None:
    if pkg in _list(adb, "-d"):
        return "disabled"
    if pkg in _list(adb):
        return "enabled"
    if pkg in _list(adb, "-u"):
        return "uninstalled"
    return None


# --- capture -------------------------------------------------------------------

def capture(adb, action: Action) -> object:
    p, t = action.params, action.type
    if t == "setting":
        return _get(adb, ["settings", "get", p["namespace"], p["key"]])
    if t == "device_config":
        return _get(adb, ["device_config", "get", p["namespace"], p["key"]])
    if t in ("package_disable", "package_uninstall"):
        return package_state(adb, p["package"])
    if t == "appops":
        return _appops_mode(adb, p["package"], p["op"])
    if t == "standby_bucket":
        return _bucket(adb, p["package"])
    return None


def _appops_mode(adb, pkg: str, op: str) -> str | None:
    out = adb.shell(["cmd", "appops", "get", pkg, op]).out
    for line in out.splitlines():
        if line.startswith(f"{op}:"):
            return line.split(":", 1)[1].split(";", 1)[0].strip()
    return None


def _bucket(adb, pkg: str) -> str | None:
    raw = adb.shell(["am", "get-standby-bucket", pkg]).out.strip()
    try:
        return _BUCKET_NAMES.get(int(raw))
    except ValueError:
        return None


# --- applicability ---------------------------------------------------------------

def is_applicable(adb, action: Action) -> str | None:
    pkg = action.package
    if not pkg:
        return None
    st = package_state(adb, pkg)
    if st is None:
        return REASON_MISSING
    if st == "uninstalled":
        return REASON_ALREADY_REMOVED
    return None


# --- apply / verify ----------------------------------------------------------------

def apply(adb, action: Action) -> None:
    p, t = action.params, action.type
    if t == "setting":
        _run(adb, ["settings", "put", p["namespace"], p["key"], p["value"]])
    elif t == "device_config":
        _run(adb, ["device_config", "put", p["namespace"], p["key"], p["value"]])
    elif t == "package_disable":
        _run(adb, ["pm", "disable-user", "--user", "0", p["package"]])
    elif t == "package_uninstall":
        _run(adb, ["pm", "uninstall", "-k", "--user", "0", p["package"]])
    elif t == "appops":
        _run(adb, ["cmd", "appops", "set", p["package"], p["op"], p["mode"]])
    elif t == "standby_bucket":
        _run(adb, ["am", "set-standby-bucket", p["package"], p["bucket"]])
    elif t == "compile":
        mode = p.get("mode", "speed-profile")
        target = ["-f", p["package"]] if p.get("package") else ["-a"]
        _run(adb, ["cmd", "package", "compile", "-m", mode, *target])
    else:
        raise AdbError(f"unknown action type {t}")


def verify(adb, action: Action) -> bool:
    p, t = action.params, action.type
    if t == "setting":
        return _get(adb, ["settings", "get", p["namespace"], p["key"]]) == p["value"]
    if t == "device_config":
        return _get(adb, ["device_config", "get", p["namespace"], p["key"]]) == p["value"]
    if t == "package_disable":
        return p["package"] in _list(adb, "-d")
    if t == "package_uninstall":
        return p["package"] not in _list(adb)
    if t == "appops":
        return _appops_mode(adb, p["package"], p["op"]) == p["mode"]
    if t == "standby_bucket":
        return _bucket(adb, p["package"]) == p["bucket"]
    return True


# --- revert -------------------------------------------------------------------------

def revert(adb, action: Action, prior: object) -> str | None:
    p, t = action.params, action.type
    if t in ("setting", "device_config"):
        base = ["settings"] if t == "setting" else ["device_config"]
        if prior is None:
            _run(adb, [*base, "delete", p["namespace"], p["key"]])
        else:
            _run(adb, [*base, "put", p["namespace"], p["key"], str(prior)])
        return None
    if t == "compile":
        return None
    pkg = p["package"]
    current = package_state(adb, pkg)
    if current is None:
        return REASON_GONE
    if t == "package_disable":
        if prior == "enabled" and current != "enabled":
            _run(adb, ["pm", "enable", pkg])
        elif prior == "uninstalled" and current != "uninstalled":
            _run(adb, ["pm", "uninstall", "-k", "--user", "0", pkg])
        return None
    if t == "package_uninstall":
        if prior in ("enabled", "disabled") and current == "uninstalled":
            _run(adb, ["cmd", "package", "install-existing", pkg])
        if prior == "disabled":
            _run(adb, ["pm", "disable-user", "--user", "0", pkg])
        return None
    if current == "uninstalled":
        return REASON_GONE
    if t == "appops":
        _run(adb, ["cmd", "appops", "set", pkg, p["op"], str(prior or "default")])
    elif t == "standby_bucket":
        _run(adb, ["am", "set-standby-bucket", pkg, str(prior or "active")])
    return None
