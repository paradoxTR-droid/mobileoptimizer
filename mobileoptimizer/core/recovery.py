"""Snapshot-free recovery: re-enable every package the profile knows, reset animations."""

from __future__ import annotations

from .adb import AdbDisconnected, AdbError
from .executors import _run, package_state

_ANIM_KEYS = ("window_animation_scale", "transition_animation_scale", "animator_duration_scale")


def recover(adb, profile) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in profile.actions.values():
        pkg = a.package
        if a.type not in ("package_disable", "package_uninstall") or not pkg or pkg in seen:
            continue
        seen.add(pkg)
        try:
            st = package_state(adb, pkg)
            if st is None:
                results.append((f"package:{pkg}", "cihazda yok"))
                continue
            if st == "uninstalled":
                _run(adb, ["cmd", "package", "install-existing", pkg])
                st = package_state(adb, pkg)
            if st == "disabled":
                _run(adb, ["pm", "enable", pkg])
            results.append((f"package:{pkg}", "tamam"))
        except AdbDisconnected:
            raise
        except AdbError as e:
            results.append((f"package:{pkg}", f"hata: {e}"))
    for key in _ANIM_KEYS:
        try:
            _run(adb, ["settings", "put", "global", key, "1.0"])
            results.append((f"setting:global:{key}", "tamam"))
        except AdbDisconnected:
            raise
        except AdbError as e:
            results.append((f"setting:global:{key}", f"hata: {e}"))
    return results
