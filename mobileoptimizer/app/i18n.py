"""UI strings. Only Turkish for v1; English is a second YAML file later."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

LOCALE_DIR = Path(__file__).resolve().parent.parent / "locale"


@lru_cache(maxsize=None)
def load_strings(lang: str = "tr") -> dict[str, str]:
    return yaml.safe_load((LOCALE_DIR / f"{lang}.yaml").read_text(encoding="utf-8"))


def t(key: str, **kw) -> str:
    text = load_strings()[key]  # KeyError on purpose: a missing string is a bug
    return text.format(**kw).strip() if kw else text.strip()
