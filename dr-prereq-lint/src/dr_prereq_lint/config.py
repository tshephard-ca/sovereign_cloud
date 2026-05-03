"""Threshold and severity configuration."""

from __future__ import annotations

from copy import deepcopy
from importlib import resources
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "window_hours": 24,
    "min_query_count": 2,
    "max_examples_per_finding": 5,
    "max_source_rows_per_finding": 20,
    "high_confidence_min_clients": 2,
    "repeated_observation_min_count": 5,
    "unmapped_client_warning_pct": 20,
    "require_resolver_identity_for_pass": True,
    "include_external_by_default": False,
    "severity": {
        "directory_role_missing": "CRITICAL",
        "kerberos_role_missing": "CRITICAL",
        "dns_resolver_missing": "CRITICAL",
        "specific_target_missing": "CRITICAL",
        "known_prereq_missing": "WARNING",
        "known_prereq_high_volume_missing": "CRITICAL",
        "heuristic_prereq_missing": "REVIEW",
    },
}


POLICY_PACKS = {
    "small_environment": "small_environment.yml",
    "enterprise": "enterprise.yml",
    "education": "education.yml",
    "healthcare": "healthcare.yml",
    "public_sector": "public_sector.yml",
    "isolated_recovery_lab": "isolated_recovery_lab.yml",
}


def merge_config(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | Path | None = None, *, policy_pack: str | None = None) -> dict[str, Any]:
    config = deepcopy(DEFAULT_CONFIG)
    if policy_pack:
        config = merge_config(config, load_policy_pack(policy_pack))
    if path is None:
        return config
    with Path(path).open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError("configuration must be a YAML mapping")
    return merge_config(config, loaded)


def load_policy_pack(name: str) -> dict[str, Any]:
    pack_name = name.strip()
    filename = POLICY_PACKS.get(pack_name, pack_name)
    try:
        content = resources.files("dr_prereq_lint.policy_packs").joinpath(filename).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        valid = ", ".join(sorted(POLICY_PACKS))
        raise ValueError(f"unknown policy pack {name!r}; valid packs: {valid}") from exc
    loaded = yaml.safe_load(content) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"policy pack {name!r} must be a YAML mapping")
    return loaded
