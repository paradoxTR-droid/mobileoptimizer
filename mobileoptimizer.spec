# PyInstaller spec: one folder (--onedir), never --onefile (onefile triggers more antivirus false positives).
import sys
from pathlib import Path

ROOT = Path(SPECPATH)
PLAT = "windows" if sys.platform == "win32" else "linux"

a = Analysis(
    [str(ROOT / "scripts" / "launch.py")],
    pathex=[str(ROOT)],
    datas=[
        (str(ROOT / "mobileoptimizer" / "profiles"), "mobileoptimizer/profiles"),
        (str(ROOT / "mobileoptimizer" / "locale"), "mobileoptimizer/locale"),
        (str(ROOT / "vendor" / "adb" / PLAT), f"vendor/adb/{PLAT}"),
        (str(ROOT / "LICENSE"), "."),
    ],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="MobileOptimizer", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="MobileOptimizer")
