"""Load and validate brand profiles (YAML)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .actions import ACTION_TYPES, CATEGORIES, PARAMS, RISKS, Action
from .blacklist import is_blocked

SHIPPED_DIR = Path(__file__).resolve().parent.parent / "profiles"

_PKG = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$")
_IDENT = re.compile(r"^[A-Za-z0-9_.\-]+$")
_VALUE = re.compile(r"^[A-Za-z0-9_.,:\-]*$")
_SETTING_NS = ("global", "system", "secure")
_BUCKETS = ("active", "working_set", "frequent", "rare", "restricted")

_TOP_KEYS = {"brand", "match", "extends", "blacklist_add", "actions", "presets"}
_COMMON_KEYS = {"id", "type", "title", "description", "category", "risk", "verified",
                "min_sdk", "max_sdk", "rom", "source"}


class ProfileError(Exception):
    pass


@dataclass(frozen=True)
class Profile:
    name: str
    brand: str
    match_manufacturers: tuple[str, ...]
    actions: dict[str, Action]
    presets: dict[str, tuple[str, ...]]
    blacklist_add: frozenset[str]


def _err(where: str, msg: str) -> ProfileError:
    return ProfileError(f"{where}: {msg}")


def _parse_action(raw: dict, origin: str) -> Action:
    if not isinstance(raw, dict):
        raise _err(origin, "action must be a mapping")
    aid = str(raw.get("id", "?"))
    where = f"{origin}/{aid}"
    t = raw.get("type")
    if t not in ACTION_TYPES:
        raise _err(where, f"unknown type {t!r}")
    required, optional = PARAMS[t]
    unknown = set(raw) - _COMMON_KEYS - set(required) - set(optional)
    if unknown:
        raise _err(where, f"unknown keys {sorted(unknown)}")
    for k in ("id", "title", "description", "category", "risk"):
        if not raw.get(k):
            raise _err(where, f"missing {k}")
    if not _IDENT.match(aid):
        raise _err(where, "bad id")
    if raw["category"] not in CATEGORIES:
        raise _err(where, f"bad category {raw['category']!r}")
    if raw["risk"] not in RISKS:
        raise _err(where, f"bad risk {raw['risk']!r}")
    params = {}
    for k in required:
        if k not in raw:
            raise _err(where, f"missing {k}")
    for k in (*required, *optional):
        if k in raw:
            params[k] = str(raw[k])
    for k, v in params.items():
        if k == "package":
            if not _PKG.match(v):
                raise _err(where, f"bad package name {v!r}")
        elif k == "value":
            if not _VALUE.match(v):
                raise _err(where, f"bad value {v!r}")
        elif not _IDENT.match(v):
            raise _err(where, f"bad {k} {v!r}")
    if t == "setting" and params["namespace"] not in _SETTING_NS:
        raise _err(where, f"bad namespace {params['namespace']!r}")
    if t == "standby_bucket" and params["bucket"] not in _BUCKETS:
        raise _err(where, f"bad bucket {params['bucket']!r}")
    if t == "package_uninstall" and raw["risk"] != "expert":
        raise _err(where, "package_uninstall requires risk: expert")
    rom = raw.get("rom", ())
    rom = (rom,) if isinstance(rom, str) else tuple(rom)
    return Action(
        id=aid, type=t, title=str(raw["title"]), description=str(raw["description"]),
        category=raw["category"], risk=raw["risk"], params=params,
        min_sdk=raw.get("min_sdk"), max_sdk=raw.get("max_sdk"), rom=rom,
        verified=bool(raw.get("verified", False)), source=raw.get("source"), origin=origin,
    )


def _read(path: Path) -> dict:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        raise ProfileError(f"{path.name}: {e}") from e
    if not isinstance(doc, dict):
        raise ProfileError(f"{path.name}: top level must be a mapping")
    unknown = set(doc) - _TOP_KEYS
    if unknown:
        raise ProfileError(f"{path.name}: unknown keys {sorted(unknown)}")
    return doc


def load_profile(path: Path, profiles_dir: Path, _seen: tuple[str, ...] = ()) -> Profile:
    name = path.stem
    if name in _seen:
        raise ProfileError(f"{name}: extends cycle")
    doc = _read(path)
    actions: dict[str, Action] = {}
    blacklist: set[str] = set()
    presets: dict[str, tuple[str, ...]] = {}
    parent_name = doc.get("extends")
    if parent_name:
        parent = load_profile(Path(profiles_dir) / f"{parent_name}.yaml", profiles_dir, (*_seen, name))
        actions.update(parent.actions)
        blacklist |= parent.blacklist_add
    for pkg in doc.get("blacklist_add") or ():
        if not _PKG.match(str(pkg)):
            raise ProfileError(f"{name}: bad blacklist package {pkg!r}")
        blacklist.add(str(pkg))
    for raw in doc.get("actions") or ():
        a = _parse_action(raw, name)
        if a.id in actions:
            raise _err(f"{name}/{a.id}", "duplicate id")
        actions[a.id] = a
    for a in actions.values():
        if a.package and is_blocked(a.package, blacklist):
            raise _err(f"{a.origin}/{a.id}", f"blacklisted package {a.package}")
    for preset, ids in (doc.get("presets") or {}).items():
        for aid in ids:
            a = actions.get(aid)
            if a is None:
                raise _err(f"{name}/preset {preset}", f"unknown action {aid}")
            if a.risk != "safe" or not a.verified or a.type == "package_uninstall":
                raise _err(f"{name}/preset {preset}", f"{aid} must be safe, verified and not uninstall")
        presets[preset] = tuple(ids)
    match = doc.get("match") or [name]
    return Profile(name=name, brand=str(doc.get("brand", name)),
                   match_manufacturers=tuple(str(m).lower() for m in match),
                   actions=actions, presets=presets, blacklist_add=frozenset(blacklist))


def load_all(profiles_dir: Path) -> dict[str, Profile]:
    profiles_dir = Path(profiles_dir)
    return {p.stem: load_profile(p, profiles_dir) for p in sorted(profiles_dir.glob("*.yaml"))}


def pick_profile(profiles: dict[str, Profile], info) -> Profile:
    for p in profiles.values():
        if p.name == "generic":
            continue
        if info.manufacturer in p.match_manufacturers or info.brand in p.match_manufacturers:
            return p
    return profiles["generic"]
