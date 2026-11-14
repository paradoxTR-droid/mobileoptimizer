"""Action model: one reversible change on the phone."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Mapping

ACTION_TYPES = ("setting", "package_disable", "package_uninstall", "appops",
                "standby_bucket", "compile", "device_config")
TEMPORARY_TYPES = frozenset({"standby_bucket", "device_config", "compile"})
CATEGORIES = ("performance", "battery", "cleanup")
RISKS = ("safe", "careful", "expert")

# required / optional params per type
PARAMS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "setting": (("namespace", "key", "value"), ()),
    "package_disable": (("package",), ()),
    "package_uninstall": (("package",), ()),
    "appops": (("package", "op", "mode"), ()),
    "standby_bucket": (("package", "bucket"), ()),
    "compile": ((), ("mode", "package")),
    "device_config": (("namespace", "key", "value"), ()),
}


@dataclass(frozen=True)
class Action:
    id: str
    type: str
    title: str
    description: str
    category: str
    risk: str
    params: Mapping[str, str] = field(default_factory=dict)
    min_sdk: int | None = None
    max_sdk: int | None = None
    rom: tuple[str, ...] = ()
    verified: bool = False
    source: str | None = None
    origin: str = ""

    @property
    def temporary(self) -> bool:
        return self.type in TEMPORARY_TYPES

    @property
    def package(self) -> str | None:
        return self.params.get("package")

    @property
    def target(self) -> str:
        p = self.params
        if self.type == "setting":
            return f"setting:{p['namespace']}:{p['key']}"
        if self.type in ("package_disable", "package_uninstall"):
            return f"package:{p['package']}"
        if self.type == "appops":
            return f"appops:{p['package']}:{p['op']}"
        if self.type == "standby_bucket":
            return f"bucket:{p['package']}"
        if self.type == "device_config":
            return f"device_config:{p['namespace']}:{p['key']}"
        return f"compile:{p.get('package', '*')}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["params"] = dict(self.params)
        d["rom"] = list(self.rom)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        d = dict(d)
        d["params"] = dict(d.get("params", {}))
        d["rom"] = tuple(d.get("rom", ()))
        return cls(**d)
