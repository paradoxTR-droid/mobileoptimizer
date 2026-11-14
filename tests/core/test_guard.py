from mobileoptimizer.core.blacklist import CORE_BLACKLIST
from mobileoptimizer.core.guard import blocked_set, device_critical_packages
from mobileoptimizer.core.profiles import Profile
from tests.fakes import FakeAdb


def _fake():
    fa = FakeAdb()
    fa.roles = {"DIALER": "com.samsung.android.dialer", "SMS": "com.samsung.android.messaging",
                "HOME": "com.sec.android.app.launcher"}
    fa.settings[("secure", "default_input_method")] = "com.samsung.android.honeyboard/.service.HoneyBoardService"
    fa.home = "com.sec.android.app.launcher/.activities.LauncherActivity"
    return fa


def test_collects_roles_ime_home():
    got = device_critical_packages(_fake())
    assert {"com.samsung.android.dialer", "com.samsung.android.messaging",
            "com.sec.android.app.launcher", "com.samsung.android.honeyboard"} <= got


def test_failed_lookup_ignored():
    fa = FakeAdb()
    fa.roles_fail = True
    got = device_critical_packages(fa)
    assert "" not in got
    assert got == frozenset()


def test_blocked_set_unions_all_layers():
    p = Profile("samsung", "samsung", ("samsung",), {}, {}, frozenset({"com.sec.android.app.camera"}))
    got = blocked_set(_fake(), p)
    assert CORE_BLACKLIST <= got
    assert {"com.sec.android.app.camera", "com.samsung.android.dialer"} <= got
