import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mobileoptimizer.app.i18n import t  # noqa: E402
from mobileoptimizer.app.window import MainWindow  # noqa: E402
from mobileoptimizer.core.profiles import SHIPPED_DIR  # noqa: E402
from mobileoptimizer.core.snapshot import SnapshotStore  # noqa: E402
from tests.fakes import FakeAdb  # noqa: E402


def test_smartscreen_guide_strings_exist():
    text = t("guide.smartscreen")
    assert "Ek bilgi" in text and "Yine de çalıştır" in text
    assert "certutil -hashfile" in text


def test_help_menu_has_smartscreen_entry(qtbot, tmp_path):
    w = MainWindow(lambda s: FakeAdb(), SnapshotStore(tmp_path), SHIPPED_DIR)
    qtbot.addWidget(w)
    labels = [a.text() for a in w.help_btn.menu().actions()]
    assert t("help.smartscreen") in labels
