"""Put adb into vendor/adb/<windows|linux>/ for packaging.

    python scripts/fetch_platform_tools.py --platform linux --sdk ~/Android/Sdk
    python scripts/fetch_platform_tools.py --platform windows            # downloads from Google

Downloads are checked against PINNED_SHA256. A missing pin stops the script and prints the hash:
compare it with a second, independent download, then commit it into PINNED_SHA256.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

VERSION = "r35.0.2"
URL = "https://dl.google.com/android/repository/platform-tools_{v}-{plat}.zip"
PINNED_SHA256: dict[str, str | None] = {"windows": None, "linux": None}
FILES = {
    "windows": ["adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll", "NOTICE.txt"],
    "linux": ["adb", "NOTICE.txt"],
}
ROOT = Path(__file__).resolve().parents[1]


def _dest(plat: str) -> Path:
    d = ROOT / "vendor" / "adb" / plat
    d.mkdir(parents=True, exist_ok=True)
    return d


def from_sdk(plat: str, sdk: Path) -> None:
    src = sdk / "platform-tools"
    dest = _dest(plat)
    for name in FILES[plat]:
        shutil.copy2(src / name, dest / name)
    if plat == "linux":
        (dest / "adb").chmod(0o755)


def from_download(plat: str) -> None:
    url = URL.format(v=VERSION, plat=plat)
    data = urllib.request.urlopen(url, timeout=120).read()
    digest = hashlib.sha256(data).hexdigest()
    pinned = PINNED_SHA256[plat]
    if pinned is None:
        sys.exit(f"no pinned SHA-256 for {plat}. Downloaded {url}\n  sha256={digest}\n"
                 "Verify it independently, then set PINNED_SHA256 in this script.")
    if digest != pinned:
        sys.exit(f"SHA-256 mismatch for {url}: got {digest}, expected {pinned}")
    dest = _dest(plat)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in FILES[plat]:
            (dest / name).write_bytes(zf.read(f"platform-tools/{name}"))
    if plat == "linux":
        (dest / "adb").chmod(0o755)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--platform", choices=sorted(FILES), default="windows" if sys.platform == "win32" else "linux")
    ap.add_argument("--sdk", type=Path, help="copy from a local Android SDK instead of downloading")
    args = ap.parse_args()
    if args.sdk:
        from_sdk(args.platform, args.sdk.expanduser())
    else:
        from_download(args.platform)
    print(f"adb ready in {_dest(args.platform)}")


if __name__ == "__main__":
    main()
