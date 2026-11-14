from mobileoptimizer.core.actions import Action
from mobileoptimizer.core.profiles import Profile
from mobileoptimizer.core.recovery import recover
from tests.fakes import FakeAdb


def P(*pkgs):
    acts = {}
    for i, (t, pkg) in enumerate(pkgs):
        acts[f"a{i}"] = Action(id=f"a{i}", type=t, title="t", description="d", category="cleanup",
                               risk="expert" if t == "package_uninstall" else "safe",
                               params={"package": pkg}, verified=True)
    return Profile("x", "x", ("x",), acts, {}, frozenset())


def test_recover_reenables_disabled_and_reinstalls_uninstalled():
    fa = FakeAdb()
    fa.packages = {"com.a.one": "disabled", "com.b.two": "uninstalled", "com.c.three": "enabled"}
    fa.system_image = set(fa.packages)
    recover(fa, P(("package_disable", "com.a.one"), ("package_uninstall", "com.b.two"),
                  ("package_disable", "com.c.three"), ("package_disable", "com.not.here")))
    assert fa.packages == {"com.a.one": "enabled", "com.b.two": "enabled", "com.c.three": "enabled"}


def test_recover_resets_animation_scales():
    fa = FakeAdb()
    for k in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
        fa.settings[("global", k)] = "0.5"
    recover(fa, P())
    assert {v for (ns, k), v in fa.settings.items()} == {"1.0"}
