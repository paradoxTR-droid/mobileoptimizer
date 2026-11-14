"""Build dist/MobileOptimizer-<version>-<platform>.zip and its .sha256.

    python scripts/fetch_platform_tools.py ...   # first
    python scripts/build.py
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tomllib
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parents[1]
PLAT = "windows" if sys.platform == "win32" else "linux"


def main() -> None:
    adb = ROOT / "vendor" / "adb" / PLAT / ("adb.exe" if PLAT == "windows" else "adb")
    if not adb.exists():
        sys.exit(f"{adb} missing: run scripts/fetch_platform_tools.py first")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    PyInstaller.__main__.run([str(ROOT / "mobileoptimizer.spec"), "--noconfirm", "--clean",
                              "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build")])
    base = ROOT / "dist" / f"MobileOptimizer-{version}-{PLAT}"
    zip_path = Path(shutil.make_archive(str(base), "zip", ROOT / "dist", "MobileOptimizer"))
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    zip_path.with_name(zip_path.name + ".sha256").write_text(f"{digest}  {zip_path.name}\n")
    print(f"{zip_path}\nsha256 {digest}")


if __name__ == "__main__":
    main()
