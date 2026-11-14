import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from mobileoptimizer.app.i18n import load_strings, t  # noqa: E402
from mobileoptimizer.app.window import MainWindow  # noqa: E402
from mobileoptimizer.core.adb import DeviceEntry  # noqa: E402
from mobileoptimizer.core.profiles import SHIPPED_DIR, load_all  # noqa: E402
from mobileoptimizer.core.session import build_preview, run  # noqa: E402
from mobileoptimizer.core.device import detect  # noqa: E402
from mobileoptimizer.core.snapshot import SnapshotStore  # noqa: E402
from tests.fakes import FakeAdb  # noqa: E402

APP_DIR = Path(__file__).resolve().parents[2] / "mobileoptimizer" / "app"


def samsung_fake():
    fa = FakeAdb("R5CX1")
    fa.props = {"ro.product.manufacturer": "samsung", "ro.product.brand": "samsung",
                "ro.product.model": "SM-A256E", "ro.product.marketname": "Galaxy A25",
                "ro.build.version.release": "14", "ro.build.version.sdk": "34",
                "ro.build.version.oneui": "60100"}
    for k in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
        fa.settings[("global", k)] = "1.0"
    fa.packages = {"com.samsung.android.app.spage": "enabled"}
    fa.system_image = set(fa.packages)
    fa.device_list = [DeviceEntry("R5CX1", "device")]
    return fa


@pytest.fixture
def win(qtbot, tmp_path):
    fa = samsung_fake()
    w = MainWindow(lambda serial: fa, SnapshotStore(tmp_path), SHIPPED_DIR)
    w.fa = fa
    qtbot.addWidget(w)
    return w


def to_device(w, qtbot):
    w.connect_page.poll()
    qtbot.waitUntil(lambda: w.stack.currentWidget() is w.device_page and w.device_page.next_btn.isEnabled())


def to_preview(w, qtbot, preset="balanced"):
    to_device(w, qtbot)
    w.device_page.next_btn.click()
    w.profile_page.radios[preset].setChecked(True)
    w.profile_page.next_btn.click()
    qtbot.waitUntil(lambda: w.stack.currentWidget() is w.preview_page and w.preview_page.list_apply.count() > 0)


def test_full_flow_apply_and_report(win, qtbot):
    to_device(win, qtbot)
    assert "Galaxy A25" in win.device_page.name_label.text()
    win.device_page.next_btn.click()
    win.profile_page.radios["balanced"].setChecked(True)
    win.profile_page.next_btn.click()
    qtbot.waitUntil(lambda: win.preview_page.list_apply.count() == 4)
    win.preview_page.ack.setChecked(True)
    win.preview_page.apply_btn.click()
    qtbot.waitUntil(lambda: win.stack.currentWidget() is win.report_page, timeout=5000)
    assert win.fa.settings[("global", "window_animation_scale")] == "0.5"
    assert win.report_page.list.count() == 4
    assert "uygulandı (zamanla sıfırlanabilir)" in "\n".join(
        win.report_page.list.item(i).text() for i in range(win.report_page.list.count()))
    assert len(win.store.list("R5CX1")) == 1


def test_apply_disabled_until_backup_ack(win, qtbot):
    to_preview(win, qtbot)
    assert t("preview.backup_warning") in win.preview_page.warning.text()
    assert not win.preview_page.apply_btn.isEnabled()
    win.preview_page.ack.setChecked(True)
    assert win.preview_page.apply_btn.isEnabled()


def test_connect_page_unauthorized_hint(win, qtbot):
    win.fa.device_list = [DeviceEntry("R5CX1", "unauthorized")]
    win.connect_page.poll()
    qtbot.waitUntil(lambda: win.connect_page.hint.text() == t("connect.unauthorized"))
    assert win.stack.currentWidget() is win.connect_page


def test_connect_page_picker_for_two_devices(win, qtbot):
    win.fa.device_list = [DeviceEntry("R5CX1", "device"), DeviceEntry("OTHER", "device")]
    win.connect_page.poll()
    qtbot.waitUntil(lambda: win.connect_page.picker.count() == 2)
    assert win.stack.currentWidget() is win.connect_page
    win.connect_page.picker.setCurrentRow(0)
    win.connect_page.pick_btn.click()
    qtbot.waitUntil(lambda: win.stack.currentWidget() is win.device_page)


def test_expert_requires_confirm(win, qtbot):
    to_device(win, qtbot)
    win.device_page.next_btn.click()
    win.profile_page.radios["custom"].setChecked(True)
    win.profile_page.next_btn.click()
    assert win.stack.currentWidget() is win.custom_page
    box = win.custom_page.boxes["sam_free_uninstall"]
    asked = []
    win.confirm = lambda text: (asked.append(text), False)[1]
    box.setChecked(True)
    assert not box.isChecked() and asked == [t("custom.expert_confirm")]
    win.confirm = lambda text: True
    box.setChecked(True)
    assert box.isChecked()


def test_custom_badges(win, qtbot):
    to_device(win, qtbot)
    win.device_page.next_btn.click()
    win.profile_page.radios["custom"].setChecked(True)
    win.profile_page.next_btn.click()
    assert t("badge.temporary") in win.custom_page.boxes["compile_all"].text()
    assert t("badge.unverified") in win.custom_page.boxes["sam_tips"].text()


def test_history_shows_chain_count(win, qtbot):
    fa, store = win.fa, win.store
    profile = load_all(SHIPPED_DIR)["samsung"]
    info = detect(fa)
    for _ in range(2):
        run(fa, build_preview(fa, profile, info, frozenset(), preset="balanced"), store, "R5CX1", "samsung", "balanced")
    to_device(win, qtbot)
    win.history_btn.click()
    assert win.stack.currentWidget() is win.history_page
    assert win.history_page.list.count() == 2
    texts = []
    win.confirm = lambda text: (texts.append(text), False)[1]
    win.history_page.list.setCurrentRow(0)  # oldest
    win.history_page.undo_btn.click()
    assert texts == [t("history.chain", n=2)]


def test_all_tr_keys_exist():
    strings = load_strings()
    used = set()
    for p in APP_DIR.rglob("*.py"):
        used |= set(re.findall(r"""\bt\(\s*["']([^"']+)["']""", p.read_text(encoding="utf-8")))
    assert used, "no t() calls found"
    assert sorted(used - strings.keys()) == []


def test_dynamic_tr_keys_exist():
    from mobileoptimizer.core.actions import CATEGORIES, RISKS
    strings = load_strings()
    dynamic = ({f"status.{s}" for s in ("applied", "applied_temporary", "skipped", "failed", "not_run", "reverted")}
               | {f"badge.{r}" for r in RISKS} | {f"custom.tab.{c}" for c in CATEGORIES}
               | {f"profile.{p}" for p in ("max_performance", "max_battery", "balanced", "custom")})
    assert sorted(dynamic - strings.keys()) == []


def test_history_and_undo_blocked_while_applying(win, qtbot):
    import threading
    gate = threading.Event()
    orig = win.fa._h_cmd

    def slow_compile(a):
        if a[:2] == ["package", "compile"]:
            gate.wait(10)
        return orig(a)

    win.fa._h_cmd = slow_compile
    to_preview(win, qtbot)
    win.preview_page.ack.setChecked(True)
    win.preview_page.apply_btn.click()
    qtbot.waitUntil(lambda: win.busy and bool(win.store.list("R5CX1")))
    assert not win.history_btn.isEnabled()
    asked = []
    win.confirm = lambda text: (asked.append(text), True)[1]
    snap_id = win.store.list("R5CX1")[0].id
    win.undo_snapshot(snap_id)
    assert asked == []  # refused while busy
    gate.set()
    qtbot.waitUntil(lambda: win.stack.currentWidget() is win.report_page, timeout=5000)
    assert not win.busy and win.history_btn.isEnabled()
