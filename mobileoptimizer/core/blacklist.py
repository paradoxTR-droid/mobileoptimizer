"""Packages no profile may ever touch, regardless of brand."""

from __future__ import annotations

from typing import Iterable

CORE_BLACKLIST: frozenset[str] = frozenset({
    "android",
    "com.android.systemui",
    "com.android.settings",
    "com.android.phone",
    "com.android.providers.telephony",
    "com.android.providers.settings",
    "com.android.providers.contacts",
    "com.android.providers.media",
    "com.android.server.telecom",
    "com.android.shell",
    "com.android.packageinstaller",
    "com.google.android.packageinstaller",
    "com.google.android.gms",
    "com.google.android.gsf",
    "com.android.vending",
    "com.android.permissioncontroller",
    "com.google.android.permissioncontroller",
    "com.android.bluetooth",
    "com.android.nfc",
    "com.android.networkstack",
    "com.google.android.networkstack",
    "com.android.inputdevices",
    "com.android.keychain",
})


def is_blocked(pkg: str, extra: Iterable[str] = ()) -> bool:
    return pkg in CORE_BLACKLIST or pkg in set(extra)
