"""Main window: header (history, help), status line, page stack."""

from __future__ import annotations

from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox, QPushButton, QStackedWidget,
                               QToolButton, QVBoxLayout, QWidget)

from mobileoptimizer.core.adb import AdbDisconnected
from mobileoptimizer.core.profiles import load_all
from mobileoptimizer.core.snapshot import undo, undo_chain

from . import pages
from .i18n import t
from .worker import run_in_thread

# (menu label key, guide text key)
HELP_TOPICS = [("help.usb", "guide.usb_debug"), ("help.xiaomi", "guide.xiaomi_security"),
               ("help.driver", "guide.windows_driver"), ("help.smartscreen", "guide.smartscreen")]


class MainWindow(QMainWindow):
    def __init__(self, adb_factory, store, profiles_dir):
        super().__init__()
        self.setWindowTitle(t("app.title"))
        self.adb_factory, self.store = adb_factory, store
        self.profiles = load_all(profiles_dir)
        self.adb = self.info = self.profile = None
        self.blocked: frozenset[str] = frozenset()
        self.preset: str | None = None
        self._prev = None
        self.busy = False  # one phone-changing task at a time (apply, undo, recover)

        root = QWidget()
        col = QVBoxLayout(root)
        header = QHBoxLayout()
        header.addWidget(QLabel(t("app.title")))
        header.addStretch(1)
        self.history_btn = QPushButton(t("nav.history"))
        self.history_btn.clicked.connect(lambda: self.go(self.history_page))
        header.addWidget(self.history_btn)
        self.help_btn = QToolButton()
        self.help_btn.setText(t("nav.help"))
        self.help_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.help_btn)
        for label_key, text_key in HELP_TOPICS:
            menu.addAction(t(label_key), lambda k=text_key, lk=label_key: QMessageBox.information(self, t(lk), t(k)))
        self.help_btn.setMenu(menu)
        header.addWidget(self.help_btn)
        col.addLayout(header)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: #b00020;")
        col.addWidget(self.status)
        self.stack = QStackedWidget()
        col.addWidget(self.stack)
        self.setCentralWidget(root)

        self.connect_page = pages.ConnectPage(self)
        self.device_page = pages.DevicePage(self)
        self.profile_page = pages.ProfilePage(self)
        self.custom_page = pages.CustomPage(self)
        self.preview_page = pages.PreviewPage(self)
        self.apply_page = pages.ApplyPage(self)
        self.report_page = pages.ReportPage(self)
        self.history_page = pages.HistoryPage(self)
        for p in (self.connect_page, self.device_page, self.profile_page, self.custom_page, self.preview_page,
                  self.apply_page, self.report_page, self.history_page):
            self.stack.addWidget(p)
        self.go(self.connect_page)

    # --- navigation ------------------------------------------------------------
    def go(self, page) -> None:
        current = self.stack.currentWidget()
        if current is not page:
            if current is not None:
                current.on_leave()
            if page is self.history_page and current is not self.history_page:
                self._prev = current
            self.stack.setCurrentWidget(page)
        self.status.clear()
        page.on_enter()

    def back(self) -> None:
        self.go(self._prev or self.connect_page)

    def open_device(self, serial: str) -> None:
        self.adb = self.adb_factory(serial)
        self.go(self.device_page)

    def start_preview(self, preset: str | None = None, action_ids=()) -> None:
        self.preset = preset
        self.go(self.preview_page)
        self.preview_page.load(preset, action_ids)

    # --- dialogs and messages -----------------------------------------------------
    def confirm(self, text: str) -> bool:
        return QMessageBox.question(self, t("confirm.title"), text) == QMessageBox.StandardButton.Yes

    def notice(self, text: str) -> None:
        self.status.setText(text)

    def fail(self, err: Exception) -> None:
        if isinstance(err, AdbDisconnected):
            self.adb = self.info = None
            self.go(self.connect_page)
            self.notice(t("error.disconnected"))
        else:
            self.notice(t("error.generic", msg=err))

    # --- phone-changing tasks -------------------------------------------------------
    def set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.history_btn.setEnabled(not busy)
        if self.stack.currentWidget() is self.history_page:
            self.history_page.refresh()

    def run_task(self, fn, *args, on_done, on_error=None, on_progress=None) -> bool:
        """Run a task that changes the phone; refuse if one is already running."""
        if self.busy:
            return False
        self.set_busy(True)

        def done(result):
            self.set_busy(False)
            on_done(result)

        def error(err):
            self.set_busy(False)
            (on_error or self.fail)(err)

        run_in_thread(fn, *args, on_done=done, on_error=error, on_progress=on_progress)
        return True

    def undo_snapshot(self, snap_id: str) -> None:
        if self.busy:
            return
        if self.adb is None or self.info is None:
            self.notice(t("history.need_device"))
            return
        serial = self.info.serial
        chain = undo_chain(self.store, serial, snap_id)
        if not chain or not self.confirm(t("history.chain", n=len(chain))):
            return

        def done(results):
            self.notice(t("history.done", skipped=sum(1 for _, reason in results if reason)))
            if self.stack.currentWidget() is self.history_page:
                self.history_page.refresh()

        self.run_task(undo, self.adb, self.store, serial, snap_id, on_done=done)
