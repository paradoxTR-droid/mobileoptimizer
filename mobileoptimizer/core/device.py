"""Detect brand, model, Android version and vendor ROM from getprop."""

from __future__ import annotations

import re
from dataclasses import dataclass

_PROP_LINE = re.compile(r"^\[(.+?)\]: \[(.*)\]$")
_ROM_LABEL = {"oneui": "One UI", "miui": "MIUI", "hyperos": "HyperOS"}


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    manufacturer: str
    brand: str
    model: str
    android: str
    sdk: int
    rom: str
    rom_version: str


def _parse(out: str) -> dict[str, str]:
    props = {}
    for line in out.splitlines():
        m = _PROP_LINE.match(line.strip())
        if m:
            props[m.group(1)] = m.group(2)
    return props


def _oneui_version(raw: str) -> str:
    try:
        v = int(raw)
    except ValueError:
        return raw
    return f"{v // 10000}.{v // 100 % 100}"


def detect(adb) -> DeviceInfo:
    p = _parse(adb.shell(["getprop"]).out)
    if p.get("ro.build.version.oneui"):
        rom, ver = "oneui", _oneui_version(p["ro.build.version.oneui"])
    elif p.get("ro.mi.os.version.name"):  # HyperOS also sets the MIUI prop, so check it first
        rom, ver = "hyperos", p["ro.mi.os.version.name"]
    elif p.get("ro.miui.ui.version.name"):
        rom, ver = "miui", p["ro.miui.ui.version.name"]
    else:
        rom, ver = "aosp", ""
    try:
        sdk = int(p.get("ro.build.version.sdk", "0"))
    except ValueError:
        sdk = 0
    return DeviceInfo(
        serial=getattr(adb, "serial", "") or "",
        manufacturer=p.get("ro.product.manufacturer", "").lower(),
        brand=p.get("ro.product.brand", "").lower(),
        model=p.get("ro.product.marketname") or p.get("ro.product.model", ""),
        android=p.get("ro.build.version.release", ""),
        sdk=sdk,
        rom=rom,
        rom_version=ver,
    )


def display_name(info: DeviceInfo) -> str:
    parts = [f"{(info.brand or info.manufacturer).title()} {info.model}".strip()]
    if info.rom in _ROM_LABEL:
        parts.append(f"{_ROM_LABEL[info.rom]} {info.rom_version}".strip())
    parts.append(f"Android {info.android}")
    return " — ".join(parts)
