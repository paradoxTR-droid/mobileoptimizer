"""Entry point: python -m mobileoptimizer.app.main"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from mobileoptimizer.core.adb import Adb, AdbError, find_adb
from mobileoptimizer.core.paths import data_dir
from mobileoptimizer.core.profiles import SHIPPED_DIR
from mobileoptimizer.core.snapshot import SnapshotStore

from .i18n import t
from .window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    try:
        adb_path = find_adb()
    except AdbError:
        QMessageBox.critical(None, t("error.title"), t("error.adb_missing"))
        return 1
    store = SnapshotStore(data_dir() / "snapshots")
    win = MainWindow(lambda serial: Adb(adb_path, serial), store, SHIPPED_DIR)
    win.resize(760, 600)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
