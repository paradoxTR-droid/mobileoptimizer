"""Read-only check of a profile against a connected phone.

Usage: python -m mobileoptimizer.tools.verify_profile --serial <s> --profile samsung
Mark an action `verified: true` only when it prints OK on the matching test phone.
"""

from __future__ import annotations

import argparse
import sys

from mobileoptimizer.core.adb import Adb, AdbError, find_adb
from mobileoptimizer.core.executors import capture, is_applicable
from mobileoptimizer.core.profiles import SHIPPED_DIR, load_all


def report_lines(adb, profile) -> list[str]:
    lines = []
    for a in profile.actions.values():
        reason = is_applicable(adb, a)
        if reason:
            lines.append(f"{a.id} MISSING {reason}")
            continue
        prior = capture(adb, a)
        if a.type in ("setting", "device_config") and prior is None:
            lines.append(f"{a.id} NULL")  # key not set on this phone: effect unknown
        elif prior is None:
            lines.append(f"{a.id} OK")
        else:
            lines.append(f"{a.id} OK {prior}")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--profile", required=True)
    args = ap.parse_args(argv)
    try:
        adb = Adb(find_adb(), args.serial)
        profile = load_all(SHIPPED_DIR)[args.profile]
        print("\n".join(report_lines(adb, profile)))
    except (AdbError, KeyError) as e:
        print(f"hata: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
