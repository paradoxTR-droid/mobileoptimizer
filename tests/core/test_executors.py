import copy

import pytest

from mobileoptimizer.core.actions import Action
from mobileoptimizer.core.adb import AdbError
from mobileoptimizer.core.executors import apply, capture, is_applicable, revert, verify
from tests.fakes import FakeAdb

PKG = "com.facebook.appmanager"


def A(type_, **params):
    return Action(id="a", type=type_, title="t", description="d", category="cleanup",
                  risk="expert" if type_ == "package_uninstall" else "safe", params=params, verified=True)


def fake():
    fa = FakeAdb()
    fa.packages = {PKG: "enabled", "com.other.app": "disabled"}
    fa.system_image = {PKG, "com.other.app"}
    fa.settings[("global", "window_animation_scale")] = "1.0"
    fa.buckets[PKG] = 10
    fa.device_config[("device_idle", "light_after_inactive_to")] = "180000"
    return fa


def state(fa):
    return copy.deepcopy((fa.settings, fa.packages, fa.appops, fa.buckets, fa.device_config))


ROUNDTRIP = [
    A("setting", namespace="global", key="window_animation_scale", value="0.5"),
    A("package_disable", package=PKG),
    A("package_uninstall", package=PKG),
    A("appops", package=PKG, op="RUN_ANY_IN_BACKGROUND", mode="ignore"),
    A("standby_bucket", package=PKG, bucket="rare"),
    A("device_config", namespace="device_idle", key="light_after_inactive_to", value="30000"),
    A("compile", mode="speed-profile"),
]


@pytest.mark.parametrize("action", ROUNDTRIP, ids=lambda a: a.type)
def test_roundtrip(action):
    fa = fake()
    before = state(fa)
    assert is_applicable(fa, action) is None
    prior = capture(fa, action)
    apply(fa, action)
    assert verify(fa, action)
    if action.type != "compile":
        assert state(fa) != before
    assert revert(fa, action, prior) is None
    assert state(fa) == before


def test_setting_null_reverts_with_delete():
    fa = fake()
    a = A("setting", namespace="global", key="never_set_before", value="1")
    prior = capture(fa, a)
    assert prior is None
    apply(fa, a)
    revert(fa, a, prior)
    assert ("global", "never_set_before") not in fa.settings
    assert ["settings", "delete", "global", "never_set_before"] in fa.calls


def test_device_config_null_reverts_with_delete():
    fa = fake()
    a = A("device_config", namespace="activity_manager", key="max_cached_processes", value="16")
    prior = capture(fa, a)
    apply(fa, a)
    revert(fa, a, prior)
    assert ("activity_manager", "max_cached_processes") not in fa.device_config


def test_uninstall_revert_restores_disabled_state():
    fa = fake()
    a = A("package_uninstall", package="com.other.app")
    prior = capture(fa, a)
    assert prior == "disabled"
    apply(fa, a)
    assert fa.packages["com.other.app"] == "uninstalled"
    revert(fa, a, prior)
    assert fa.packages["com.other.app"] == "disabled"


def test_disable_revert_when_previously_disabled_is_noop():
    fa = fake()
    a = A("package_disable", package="com.other.app")
    prior = capture(fa, a)
    apply(fa, a)
    revert(fa, a, prior)
    assert fa.packages["com.other.app"] == "disabled"


def test_revert_package_gone_after_update_returns_reason():
    fa = fake()
    a = A("package_disable", package=PKG)
    prior = capture(fa, a)
    apply(fa, a)
    del fa.packages[PKG]
    fa.system_image.discard(PKG)
    reason = revert(fa, a, prior)
    assert reason


def test_missing_package_not_applicable():
    assert is_applicable(fake(), A("package_disable", package="com.not.here")) == "cihazda yok"


def test_already_uninstalled_not_applicable():
    fa = fake()
    fa.packages[PKG] = "uninstalled"
    assert is_applicable(fa, A("package_disable", package=PKG))


def test_apply_failure_in_stdout_raises():
    fa = fake()
    fa.pm_failure = "Failure [not installed for 0]"
    with pytest.raises(AdbError):
        apply(fa, A("package_disable", package=PKG))


def test_compile_uses_long_timeout():
    fa = fake()
    apply(fa, A("compile", mode="speed-profile"))
    assert fa.timeouts[-1] >= 1800


def test_compile_single_package_command():
    fa = fake()
    apply(fa, A("compile", mode="speed-profile", package=PKG))
    assert ["cmd", "package", "compile", "-m", "speed-profile", "-f", PKG] in fa.calls
