import os
import sys
from pathlib import Path


def data_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "MobileOptimizer"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "MobileOptimizer"
