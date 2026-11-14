"""Wizard pages: connect -> device -> profile -> (custom) -> preview -> apply -> report, plus history."""

from __future__ import annotations

import sys
from collections import Counter
from functools import partial

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QHBoxLayout, QLabel, QListWidget, QProgressBar,
                               QPushButton, QRadioButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget)

from mobileoptimizer.core.actions import CATEGORIES
from mobileoptimizer.core.adb import AdbError
from mobileoptimizer.core.device import detect, display_name
from mobileoptimizer.core.guard import blocked_set
from mobileoptimizer.core.profiles import pick_profile
from mobileoptimizer.core.recovery import recover
from mobileoptimizer.core.session import build_preview, check_drift, run
from mobileoptimizer.core.snapshot import can_undo_single, undo_single

from .i18n import t
from .worker import run_in_thread

PRESETS = ("max_performance", "max_battery", "balanced")
DRIVER_HINT_AFTER = 30  # polls (~30 s) without a phone before the Windows driver hint


def badges(action) -> str:
    parts = [t(f"badge.{action.risk}")]
    if action.temporary:
        parts.append(t("badge.temporary"))
    if not action.verified:
        parts.append(t("badge.unverified"))
    return "[" + ", ".join(parts) + "]"


def status_text(status: str) -> str:
    return t(f"status.{status}") if status != "pending" else status


def heading(text: str) -> QLabel:
    lbl = QLabel(text)
    f = lbl.font()
    f.setPointSize(f.pointSize() + 4)
    f.setBold(True)
    lbl.setFont(f)
    return lbl


def wrap(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    return lbl


class Page(QWidget):
    def __init__(self, win, title: str):
        super().__init__()
        self.w = win
        self.box = QVBoxLayout(self)
        self.box.addWidget(heading(title))

    def on_enter(self):
        pass

    def on_leave(self):
        pass

    def buttons(self, *btns) -> None:
        row = QHBoxLayout()
        row.addStretch(1)
        for b in btns:
            row.addWidget(b)
        self.box.addStretch(1)
        self.box.addLayout(row)


class ConnectPage(Page):
    def __init__(self, win):
        super().__init__(win, t("connect.title"))
        self.box.addWidget(wrap(t("guide.usb_debug")))
        self.box.addWidget(wrap(t("guide.xiaomi_security")))
        self.hint = wrap(t("connect.waiting"))
        self.box.addWidget(self.hint)
        self.driver = wrap(t("guide.windows_driver"))
        self.driver.hide()
        self.box.addWidget(self.driver)
        self.picker = QListWidget()
        self.picker.hide()
        self.box.addWidget(self.picker)
        self.pick_btn = QPushButton(t("connect.pick_btn"))
        self.pick_btn.hide()
        self.pick_btn.clicked.connect(self._pick)
        self.buttons(self.pick_btn)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.poll)
        self._busy = False
        self._empty_polls = 0

    def on_enter(self):
        self._empty_polls = 0
        self.timer.start()

    def on_leave(self):
        self.timer.stop()

    def poll(self):
        if self._busy:
            return
        self._busy = True
        run_in_thread(self.w.adb_factory(None).devices, on_done=self._got, on_error=self._poll_error)

    def _poll_error(self, err):
        self._busy = False
        self.hint.setText(t("error.adb_missing") if isinstance(err, AdbError) else t("error.generic", msg=err))

    def _got(self, entries):
        self._busy = False
        if self.w.stack.currentWidget() is not self:
            return
        ready = [e.serial for e in entries if e.state == "device"]
        states = {e.state for e in entries}
        if "unauthorized" in states:
            self.hint.setText(t("connect.unauthorized"))
        elif "offline" in states:
            self.hint.setText(t("connect.offline"))
        elif not ready:
            self.hint.setText(t("connect.waiting"))
        if not entries:
            self._empty_polls += 1
            self.driver.setVisible(sys.platform == "win32" and self._empty_polls >= DRIVER_HINT_AFTER)
        if len(ready) == 1 and "unauthorized" not in states:
            self.w.open_device(ready[0])
        elif len(ready) > 1:
            if [self.picker.item(i).text() for i in range(self.picker.count())] != ready:
                self.picker.clear()
                self.picker.addItems(ready)
            self.hint.setText(t("connect.pick"))
            self.picker.show()
            self.pick_btn.show()

    def _pick(self):
        item = self.picker.currentItem()
        if item:
            self.w.open_device(item.text())


class DevicePage(Page):
    def __init__(self, win):
        super().__init__(win, t("device.title"))
        self.name_label = wrap(t("device.loading"))
        self.profile_label = wrap()
        self.old_label = wrap(t("device.old_android"))
        self.drift_label = wrap()
        self.drift_btn = QPushButton(t("device.reapply"))
        self.drift_btn.clicked.connect(self._reapply)
        for wdg in (self.name_label, self.profile_label, self.old_label, self.drift_label, self.drift_btn):
            self.box.addWidget(wdg)
        self.next_btn = QPushButton(t("nav.next"))
        self.next_btn.clicked.connect(lambda: self.w.go(self.w.profile_page))
        self.buttons(self.next_btn)
        self._drift: list[str] = []

    def on_enter(self):
        self.next_btn.setEnabled(False)
        self.name_label.setText(t("device.loading"))
        for wdg in (self.old_label, self.drift_label, self.drift_btn):
            wdg.hide()
        run_in_thread(self._load, self.w.adb, on_done=self._loaded, on_error=self.w.fail)

    def _load(self, adb):
        info = detect(adb)
        profile = pick_profile(self.w.profiles, info)
        return info, profile, blocked_set(adb, profile), check_drift(adb, self.w.store, info.serial)

    def _loaded(self, res):
        info, profile, blocked, drift = res
        self.w.info, self.w.profile, self.w.blocked = info, profile, blocked
        self.name_label.setText(display_name(info))
        name = t("device.generic") if profile.name == "generic" else profile.brand.title()
        self.profile_label.setText(t("device.profile", name=name))
        self.old_label.setVisible(info.sdk < 29)
        self._drift = [d for d in drift if d in profile.actions]
        if self._drift:
            self.drift_label.setText(t("device.drift", n=len(self._drift)))
            self.drift_label.show()
            self.drift_btn.show()
        self.next_btn.setEnabled(True)

    def _reapply(self):
        self.w.start_preview(action_ids=self._drift)


class ProfilePage(Page):
    def __init__(self, win):
        super().__init__(win, t("profile.title"))
        self.group = QButtonGroup(self)
        self.radios: dict[str, QRadioButton] = {}
        for key in (*PRESETS, "custom"):
            rb = QRadioButton(t(f"profile.{key}"))
            self.radios[key] = rb
            self.group.addButton(rb)
            self.box.addWidget(rb)
        self.radios["balanced"].setChecked(True)
        back = QPushButton(t("nav.back"))
        back.clicked.connect(lambda: self.w.go(self.w.device_page))
        self.next_btn = QPushButton(t("nav.next"))
        self.next_btn.clicked.connect(self._next)
        self.buttons(back, self.next_btn)

    def _next(self):
        key = next(k for k, rb in self.radios.items() if rb.isChecked())
        if key == "custom":
            self.w.go(self.w.custom_page)
        else:
            self.w.start_preview(preset=key)


class CustomPage(Page):
    def __init__(self, win):
        super().__init__(win, t("custom.title"))
        self.tabs = QTabWidget()
        self.box.addWidget(self.tabs)
        self.boxes: dict[str, QCheckBox] = {}
        back = QPushButton(t("nav.back"))
        back.clicked.connect(lambda: self.w.go(self.w.profile_page))
        self.next_btn = QPushButton(t("nav.next"))
        self.next_btn.clicked.connect(self._next)
        self.buttons(back, self.next_btn)
        self._built_for = None

    def on_enter(self):
        if self._built_for is self.w.profile:
            return
        self._built_for = self.w.profile
        self.tabs.clear()
        self.boxes.clear()
        for cat in CATEGORIES:
            inner = QWidget()
            col = QVBoxLayout(inner)
            for a in self.w.profile.actions.values():
                if a.category != cat:
                    continue
                cb = QCheckBox(f"{a.title}  {badges(a)}\n{a.description}")
                cb.setToolTip(a.description)
                if a.risk == "expert":
                    cb.toggled.connect(partial(self._expert, cb))
                self.boxes[a.id] = cb
                col.addWidget(cb)
            col.addStretch(1)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(inner)
            self.tabs.addTab(scroll, t(f"custom.tab.{cat}"))

    def _expert(self, cb: QCheckBox, on: bool):
        if on and not self.w.confirm(t("custom.expert_confirm")):
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)

    def _next(self):
        ids = [aid for aid, cb in self.boxes.items() if cb.isChecked()]
        if not ids:
            self.w.notice(t("custom.none"))
            return
        self.w.start_preview(action_ids=ids)


class PreviewPage(Page):
    def __init__(self, win):
        super().__init__(win, t("preview.title"))
        self.status = wrap()
        self.apply_head = QLabel()
        self.list_apply = QListWidget()
        self.skip_head = QLabel()
        self.list_skip = QListWidget()
        self.warning = wrap(t("preview.backup_warning"))
        self.warning.setStyleSheet("font-weight: bold;")
        self.ack = QCheckBox(t("preview.backup_ack"))
        self.ack.toggled.connect(self._update)
        for wdg in (self.status, self.apply_head, self.list_apply, self.skip_head, self.list_skip,
                    self.warning, self.ack):
            self.box.addWidget(wdg)
        back = QPushButton(t("nav.back"))
        back.clicked.connect(lambda: self.w.go(self.w.profile_page))
        self.apply_btn = QPushButton(t("preview.apply"))
        self.apply_btn.clicked.connect(self._apply)
        self.buttons(back, self.apply_btn)
        self.preview = None

    def load(self, preset, action_ids):
        self.preview = None
        self.ack.setChecked(False)
        self.list_apply.clear()
        self.list_skip.clear()
        self.status.setText(t("preview.loading"))
        self._update()
        fn = partial(build_preview, preset=preset, action_ids=tuple(action_ids))
        run_in_thread(fn, self.w.adb, self.w.profile, self.w.info, self.w.blocked,
                      on_done=self._loaded, on_error=self.w.fail)

    def _loaded(self, pv):
        self.preview = pv
        self.status.setText("" if pv.to_apply else t("preview.nothing"))
        self.apply_head.setText(t("preview.apply_head", n=len(pv.to_apply)))
        self.skip_head.setText(t("preview.skip_head", n=len(pv.skipped)))
        self.list_apply.addItems([f"{a.title}  {badges(a)}" for a in pv.to_apply])
        self.list_skip.addItems([f"{a.title} — {reason}" for a, reason in pv.skipped])
        self._update()

    def _update(self, *_):
        self.apply_btn.setEnabled(bool(self.preview and self.preview.to_apply and self.ack.isChecked()))

    def _apply(self):
        self.w.go(self.w.apply_page)
        self.w.apply_page.start(self.preview)


class ApplyPage(Page):
    def __init__(self, win):
        super().__init__(win, t("apply.title"))
        self.bar = QProgressBar()
        self.step = wrap()
        self.box.addWidget(self.bar)
        self.box.addWidget(self.step)
        self.box.addWidget(wrap(t("apply.keep_connected")))
        self.box.addStretch(1)

    def start(self, pv):
        self.bar.setRange(0, len(pv.to_apply))
        self.bar.setValue(0)
        w = self.w
        fn = partial(run, w.adb, pv, w.store, w.info.serial, w.profile.name, w.preset)
        run_in_thread(fn, on_done=self._done, on_error=w.fail, on_progress=self._progress)

    def _progress(self, i, n, action):
        self.bar.setValue(i - 1)
        self.step.setText(t("apply.step", i=i, n=n, title=action.title))

    def _done(self, res):
        snap, results = res
        self.bar.setValue(self.bar.maximum())
        self.w.go(self.w.report_page)
        self.w.report_page.show_results(snap, results)


class ReportPage(Page):
    def __init__(self, win):
        super().__init__(win, t("report.title"))
        self.summary = wrap()
        self.list = QListWidget()
        self.box.addWidget(self.summary)
        self.box.addWidget(self.list)
        self.undo_btn = QPushButton(t("report.undo"))
        self.undo_btn.clicked.connect(lambda: self.w.undo_snapshot(self.snap.id))
        done = QPushButton(t("report.done"))
        done.clicked.connect(lambda: self.w.go(self.w.profile_page))
        self.buttons(self.undo_btn, done)
        self.snap = None

    def show_results(self, snap, results):
        self.snap = snap
        c = Counter("applied" if r.status == "applied_temporary" else r.status for r in results)
        self.summary.setText(t("report.summary", applied=c["applied"], skipped=c["skipped"],
                               failed=c["failed"], not_run=c["not_run"]))
        self.list.clear()
        for r in results:
            a = self.w.profile.actions.get(r.action_id)
            title = a.title if a else r.action_id
            line = f"{title} — {status_text(r.status)}"
            if r.status in ("failed", "skipped", "not_run") and r.detail:
                line += f": {r.detail}"
            self.list.addItem(line)
        self.undo_btn.setEnabled(any(e.status in ("applied", "applied_temporary") for e in snap.entries))


class HistoryPage(Page):
    def __init__(self, win):
        super().__init__(win, t("history.title"))
        self.empty = wrap()
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._selected)
        self.entries = QListWidget()
        self.entries.currentRowChanged.connect(self._entry_selected)
        for wdg in (self.empty, self.list, self.entries):
            self.box.addWidget(wdg)
        self.undo_btn = QPushButton(t("history.undo"))
        self.undo_btn.clicked.connect(self._undo)
        self.single_btn = QPushButton(t("history.single"))
        self.single_btn.clicked.connect(self._undo_single)
        self.factory_btn = QPushButton(t("history.factory"))
        self.factory_btn.clicked.connect(self._factory)
        self.recover_btn = QPushButton(t("history.recover"))
        self.recover_btn.clicked.connect(self._recover)
        back = QPushButton(t("nav.back"))
        back.clicked.connect(self.w.back)
        self.buttons(self.undo_btn, self.single_btn, self.factory_btn, self.recover_btn, back)
        self.snaps = []

    def on_enter(self):
        self.refresh()

    def refresh(self):
        self.list.clear()
        self.entries.clear()
        self.snaps = []
        connected = self.w.adb is not None and self.w.info is not None
        if connected:
            self.snaps = self.w.store.list(self.w.info.serial)
            for s in self.snaps:
                applied = sum(e.status in ("applied", "applied_temporary") for e in s.entries)
                self.list.addItem(t("history.item", created=s.created[:19].replace("T", " "),
                                    preset=s.preset or "özel", count=applied,
                                    reverted=t("history.reverted") if s.reverted else ""))
        self.empty.setText("" if self.snaps else t("history.empty") if connected else t("history.need_device"))
        live = [s for s in self.snaps if not s.reverted]
        self.undo_btn.setEnabled(False)
        self.single_btn.setEnabled(False)
        self.factory_btn.setEnabled(bool(live))
        self.recover_btn.setEnabled(connected)

    def _current(self):
        row = self.list.currentRow()
        return self.snaps[row] if 0 <= row < len(self.snaps) else None

    def _selected(self, _row):
        s = self._current()
        self.entries.clear()
        self.undo_btn.setEnabled(bool(s and not s.reverted))
        self.single_btn.setEnabled(False)
        if s:
            for e in s.entries:
                self.entries.addItem(f"{e.action.title} — {status_text(e.status)}")

    def _entry_selected(self, row):
        s = self._current()
        ok = bool(s) and 0 <= row < len(s.entries) and can_undo_single(
            self.w.store, s.serial, s.id, s.entries[row].action.id)
        self.single_btn.setEnabled(ok)

    def _undo(self):
        s = self._current()
        if s:
            self.w.undo_snapshot(s.id)

    def _undo_single(self):
        s, row = self._current(), self.entries.currentRow()
        if not s or not 0 <= row < len(s.entries):
            return
        aid = s.entries[row].action.id
        run_in_thread(undo_single, self.w.adb, self.w.store, s.serial, s.id, aid,
                      on_done=lambda reason: (self.w.notice(t("history.done", skipped=1 if reason else 0)),
                                              self.refresh()),
                      on_error=self.w.fail)

    def _factory(self):
        live = [s for s in self.snaps if not s.reverted]
        if live:
            self.w.undo_snapshot(live[0].id)

    def _recover(self):
        if not self.w.confirm(t("history.recover_confirm")):
            return
        run_in_thread(recover, self.w.adb, self.w.profile,
                      on_done=lambda _: self.w.notice(t("history.recover_done")), on_error=self.w.fail)
