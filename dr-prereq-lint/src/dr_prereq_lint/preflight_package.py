"""Input package manifest loading for recovery preflight runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


INPUT_ALIASES = {
    "backup_inventory": ("backup_inventory", "inventory"),
    "dns_log": ("dns_log", "dns_queries", "dns_query_log"),
    "known_prereqs": ("known_prereqs", "prerequisite_catalog"),
    "resolver_hints": ("resolver_hints", "required_resolvers"),
    "answer_map": ("answer_map", "offline_answer_map"),
    "accepted_risks": ("accepted_risks",),
    "recovery_sets": ("recovery_sets",),
    "owner_map": ("owner_map",),
    "config": ("config", "thresholds", "policy"),
}


@dataclass(frozen=True)
class PreflightPackage:
    path: Path
    schema_version: str
    recovery_set: str
    inputs: dict[str, Path | None] = field(default_factory=dict)
    policy_pack: str = ""
    window_hours: int | None = None
    compare_window_hours: list[int] = field(default_factory=list)
    include_unmapped_clients: bool = False
    include_external: bool | None = None
    min_query_count: int | None = None

    def input_path(self, name: str) -> Path | None:
        return self.inputs.get(name)


def load_preflight_package(path: str | Path) -> PreflightPackage:
    package_path = Path(path)
    payload = yaml.safe_load(package_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("preflight package must be a YAML mapping")
    inputs_payload = payload.get("inputs", {})
    if not isinstance(inputs_payload, dict):
        raise ValueError("preflight package inputs must be a mapping")
    policy_payload = payload.get("policy", {})
    if policy_payload is None:
        policy_payload = {}
    if isinstance(policy_payload, str):
        inputs_payload = {**inputs_payload, "policy": policy_payload}
        policy_payload = {}
    if not isinstance(policy_payload, dict):
        raise ValueError("preflight package policy must be a mapping or policy file path")
    base = package_path.parent
    inputs = {
        canonical: _resolve_optional_path(base, _lookup_alias(inputs_payload, aliases))
        for canonical, aliases in INPUT_ALIASES.items()
    }
    recovery_set = str(payload.get("recovery_set") or policy_payload.get("recovery_set") or "").strip()
    if not recovery_set:
        raise ValueError("preflight package must declare recovery_set")
    if inputs["backup_inventory"] is None:
        raise ValueError("preflight package inputs must include backup_inventory")
    if inputs["dns_log"] is None:
        raise ValueError("preflight package inputs must include dns_queries or dns_log")
    return PreflightPackage(
        path=package_path,
        schema_version=str(payload.get("schema_version") or "1.0"),
        recovery_set=recovery_set,
        inputs=inputs,
        policy_pack=str(policy_payload.get("pack") or policy_payload.get("policy_pack") or "").strip(),
        window_hours=_optional_int(policy_payload.get("window_hours")),
        compare_window_hours=_int_list(policy_payload.get("compare_window_hours")),
        include_unmapped_clients=bool(policy_payload.get("include_unmapped_clients", False)),
        include_external=_optional_bool(policy_payload.get("include_external")),
        min_query_count=_optional_int(policy_payload.get("min_query_count")),
    )


def _lookup_alias(payload: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for alias in aliases:
        if alias in payload and payload[alias] is not None and payload[alias] != "":
            return payload[alias]
    return None


def _resolve_optional_path(base: Path, value: Any) -> Path | None:
    if value is None or value == "":
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = base / path
    return path


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _int_list(value: Any) -> list[int]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [int(item) for item in value]
    return [int(value)]
