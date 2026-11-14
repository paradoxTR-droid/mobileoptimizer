import pytest
import yaml

from mobileoptimizer.core.actions import Action
from mobileoptimizer.core.device import DeviceInfo
from mobileoptimizer.core.profiles import ProfileError, load_all, load_profile, pick_profile


def act(**kw):
    base = {"id": "anim_window", "type": "setting", "namespace": "global",
            "key": "window_animation_scale", "value": "0.5", "category": "performance",
            "risk": "safe", "verified": True, "title": "Pencere animasyonu", "description": "x"}
    base.update(kw)
    return base


def write(d, name, actions=(), presets=None, **top):
    doc = {"brand": name, "match": [name], "actions": list(actions), "presets": presets or {}}
    doc.update(top)
    (d / f"{name}.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return d / f"{name}.yaml"


def load(tmp_path, actions=(), presets=None, **top):
    return load_profile(write(tmp_path, "brand", actions, presets, **top), tmp_path)


def test_valid_profile_loads(tmp_path):
    p = load(tmp_path, [act()], {"max_performance": ["anim_window"]})
    a = p.actions["anim_window"]
    assert a.params == {"namespace": "global", "key": "window_animation_scale", "value": "0.5"}
    assert a.target == "setting:global:window_animation_scale"
    assert a.origin == "brand" and not a.temporary
    assert p.presets["max_performance"] == ("anim_window",)


def test_rejects_unknown_type(tmp_path):
    with pytest.raises(ProfileError, match="anim_window"):
        load(tmp_path, [act(type="shell")])


def test_rejects_duplicate_id_across_extends(tmp_path):
    write(tmp_path, "generic", [act()])
    with pytest.raises(ProfileError, match="anim_window"):
        load(tmp_path, [act()], extends="generic")


def test_rejects_bad_package_name(tmp_path):
    a = {"id": "p", "type": "package_disable", "package": "com.foo;rm", "category": "cleanup",
         "risk": "safe", "verified": True, "title": "t", "description": "d"}
    with pytest.raises(ProfileError, match="p"):
        load(tmp_path, [a])


def test_rejects_shell_metachar_value(tmp_path):
    with pytest.raises(ProfileError):
        load(tmp_path, [act(value="1; reboot")])


def test_uninstall_requires_expert(tmp_path):
    a = {"id": "u", "type": "package_uninstall", "package": "com.foo.bar", "category": "cleanup",
         "risk": "careful", "verified": True, "title": "t", "description": "d"}
    with pytest.raises(ProfileError, match="expert"):
        load(tmp_path, [a])


def test_preset_rejects_unverified(tmp_path):
    with pytest.raises(ProfileError, match="anim_window"):
        load(tmp_path, [act(verified=False)], {"balanced": ["anim_window"]})


def test_preset_rejects_careful(tmp_path):
    with pytest.raises(ProfileError, match="anim_window"):
        load(tmp_path, [act(risk="careful")], {"balanced": ["anim_window"]})


def test_preset_rejects_unknown_id(tmp_path):
    with pytest.raises(ProfileError, match="nope"):
        load(tmp_path, [act()], {"balanced": ["nope"]})


def test_rejects_core_blacklisted_package(tmp_path):
    a = {"id": "ui", "type": "package_disable", "package": "com.android.systemui", "category": "cleanup",
         "risk": "safe", "verified": True, "title": "t", "description": "d"}
    with pytest.raises(ProfileError, match="ui"):
        load(tmp_path, [a])


def test_rejects_brand_blacklisted_package(tmp_path):
    a = {"id": "l", "type": "package_disable", "package": "com.sec.android.app.launcher", "category": "cleanup",
         "risk": "safe", "verified": True, "title": "t", "description": "d"}
    with pytest.raises(ProfileError, match="l"):
        load(tmp_path, [a], blacklist_add=["com.sec.android.app.launcher"])


def test_rejects_blacklist_remove_key(tmp_path):
    with pytest.raises(ProfileError, match="blacklist_remove"):
        load(tmp_path, [act()], blacklist_remove=["com.android.systemui"])


def test_rejects_unknown_action_key(tmp_path):
    with pytest.raises(ProfileError, match="command"):
        load(tmp_path, [act(command="reboot")])


def test_extends_merges_generic_actions(tmp_path):
    write(tmp_path, "generic", [act()], {"balanced": ["anim_window"]})
    p = load(tmp_path, [act(id="anim_trans", key="transition_animation_scale")],
             {"balanced": ["anim_window", "anim_trans"]}, extends="generic")
    assert set(p.actions) == {"anim_window", "anim_trans"}
    assert p.actions["anim_window"].origin == "generic"
    assert p.actions["anim_trans"].origin == "brand"


def test_action_dict_roundtrip(tmp_path):
    a = load(tmp_path, [act(min_sdk=29, rom=["oneui"])]).actions["anim_window"]
    assert Action.from_dict(a.to_dict()) == a


def test_temporary_types(tmp_path):
    a = {"id": "b", "type": "standby_bucket", "package": "com.foo.bar", "bucket": "rare",
         "category": "battery", "risk": "safe", "verified": True, "title": "t", "description": "d"}
    p = load(tmp_path, [a])
    assert p.actions["b"].temporary and p.actions["b"].target == "bucket:com.foo.bar"
    assert p.actions["b"].package == "com.foo.bar"


def _info(manufacturer, brand):
    return DeviceInfo("s", manufacturer, brand, "m", "14", 34, "aosp", "")


def test_pick_profile_redmi_maps_to_xiaomi(tmp_path):
    write(tmp_path, "generic", [act()])
    write(tmp_path, "xiaomi", [], match=["xiaomi", "redmi", "poco"])
    profiles = load_all(tmp_path)
    assert pick_profile(profiles, _info("xiaomi", "redmi")).name == "xiaomi"
    assert pick_profile(profiles, _info("unknown", "poco")).name == "xiaomi"


def test_pick_profile_unknown_falls_back_generic(tmp_path):
    write(tmp_path, "generic", [act()])
    write(tmp_path, "samsung", [])
    assert pick_profile(load_all(tmp_path), _info("google", "google")).name == "generic"
