from mobileoptimizer.core.device import detect, display_name
from tests.fakes import FakeAdb


def _fake(**props):
    fa = FakeAdb("S1")
    base = {"ro.build.version.release": "14", "ro.build.version.sdk": "34"}
    fa.props = {**base, **props}
    return fa


def test_detect_samsung():
    fa = _fake(**{"ro.product.manufacturer": "samsung", "ro.product.brand": "samsung",
                  "ro.product.model": "SM-A256E", "ro.product.marketname": "Galaxy A25",
                  "ro.build.version.oneui": "60100"})
    info = detect(fa)
    assert (info.serial, info.manufacturer, info.sdk) == ("S1", "samsung", 34)
    assert (info.rom, info.rom_version) == ("oneui", "6.1")
    assert display_name(info) == "Samsung Galaxy A25 — One UI 6.1 — Android 14"


def test_detect_hyperos():
    fa = _fake(**{"ro.product.manufacturer": "Xiaomi", "ro.product.brand": "Redmi",
                  "ro.product.model": "24117RN76G", "ro.mi.os.version.name": "OS1.0",
                  "ro.miui.ui.version.name": "V816"})
    info = detect(fa)
    assert (info.rom, info.rom_version) == ("hyperos", "OS1.0")
    assert info.manufacturer == "xiaomi"


def test_detect_miui():
    fa = _fake(**{"ro.product.manufacturer": "Xiaomi", "ro.product.brand": "Redmi",
                  "ro.product.model": "M2101K6G", "ro.miui.ui.version.name": "V14"})
    info = detect(fa)
    assert (info.rom, info.rom_version) == ("miui", "V14")
    assert display_name(info) == "Redmi M2101K6G — MIUI V14 — Android 14"


def test_detect_generic():
    fa = _fake(**{"ro.product.manufacturer": "Google", "ro.product.brand": "google",
                  "ro.product.model": "Pixel 7"})
    info = detect(fa)
    assert info.rom == "aosp"
    assert display_name(info) == "Google Pixel 7 — Android 14"
