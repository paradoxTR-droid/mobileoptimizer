from pathlib import Path

from mobileoptimizer.core.profiles import load_all
from mobileoptimizer.tools.verify_profile import report_lines
from tests.fakes import FakeAdb

PROFILES_DIR = Path(__file__).resolve().parents[2] / "mobileoptimizer" / "profiles"
PRESETS = {"max_performance", "max_battery", "balanced"}
ANIM_KEYS = {"window_animation_scale", "transition_animation_scale", "animator_duration_scale"}


def test_shipped_profiles_load():
    profiles = load_all(PROFILES_DIR)
    assert {"generic", "samsung", "xiaomi"} <= profiles.keys()
    for p in profiles.values():
        assert PRESETS <= p.presets.keys()
        assert p.presets["max_performance"]


def test_balanced_has_no_refresh_bucket_or_device_config():
    for p in load_all(PROFILES_DIR).values():
        for aid in p.presets["balanced"]:
            a = p.actions[aid]
            assert a.type not in ("standby_bucket", "device_config")
            assert "refresh" not in a.params.get("key", "")


def test_presets_use_animation_scale_half():
    for p in load_all(PROFILES_DIR).values():
        for ids in p.presets.values():
            for aid in ids:
                if p.actions[aid].params.get("key") in ANIM_KEYS:
                    assert p.actions[aid].params["value"] == "0.5"


def test_xiaomi_matches_redmi_and_poco():
    assert {"xiaomi", "redmi", "poco"} <= set(load_all(PROFILES_DIR)["xiaomi"].match_manufacturers)


def test_verify_profile_report_is_read_only():
    profile = load_all(PROFILES_DIR)["generic"]
    fa = FakeAdb()
    fa.settings[("global", "window_animation_scale")] = "1.0"
    lines = report_lines(fa, profile)
    assert "anim_window OK 1.0" in lines
    assert any(l.endswith(" NULL") or " MISSING " in l for l in lines)
    writes = [c for c in fa.calls
              if c[:2] in (["settings", "put"], ["settings", "delete"], ["pm", "disable-user"], ["pm", "uninstall"],
                           ["pm", "enable"], ["device_config", "put"], ["am", "set-standby-bucket"])
              or c[:3] == ["cmd", "appops", "set"] or c[:3] == ["cmd", "package", "compile"]]
    assert writes == []
