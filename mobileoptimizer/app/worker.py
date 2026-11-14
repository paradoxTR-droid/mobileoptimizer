"""Run blocking adb work off the UI thread; results come back on the UI thread."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

_live: set = set()  # keep signal objects alive until their task finishes


class _Signals(QObject):
    done = Signal(object)
    error = Signal(object)
    progress = Signal(object)


class _Task(QRunnable):
    def __init__(self, fn, args, signals: _Signals, with_progress: bool):
        super().__init__()
        self.fn, self.args, self.s, self.with_progress = fn, args, signals, with_progress

    def run(self):
        try:
            kw = {"on_progress": lambda *a: self.s.progress.emit(a)} if self.with_progress else {}
            result = self.fn(*self.args, **kw)
        except Exception as e:  # noqa: BLE001 - every failure must reach the UI
            self.s.error.emit(e)
        else:
            self.s.done.emit(result)


def run_in_thread(fn, *args, on_done, on_error, on_progress=None) -> None:
    s = _Signals()
    s.done.connect(on_done)
    s.error.connect(on_error)
    if on_progress:
        s.progress.connect(lambda a: on_progress(*a))
    _live.add(s)
    s.done.connect(lambda _: _live.discard(s))
    s.error.connect(lambda _: _live.discard(s))
    QThreadPool.globalInstance().start(_Task(fn, args, s, on_progress is not None))
