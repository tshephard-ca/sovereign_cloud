from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import CompilerConfig


DEFAULT_CONFIG = {
    "default_ttl_minutes": 30,
    "max_ttl_minutes": 60,
    "p0_max_ttl_minutes": 30,
    "p1_max_ttl_minutes": 30,
    "p2_max_ttl_minutes": 20,
    "p3_max_ttl_minutes": 15,
    "p4_max_ttl_minutes": 15,
    "null_route_max_ttl_minutes": 10,
    "max_actions": 50,
    "allow_name_match": False,
    "require_rollback": True,
    "require_ttl": True,
    "fail_on_p0_shed": True,
    "fail_on_unmatched_event_targets": False,
    "default_mode": "REVIEW_ONLY",
    "source_blocking": {
        "enabled_by_default": False,
        "min_ipv4_prefix_length": 24,
        "min_ipv6_prefix_length": 64,
        "require_spoofing_likely_false": True,
    },
    "null_route": {
        "enabled_by_default": False,
        "p0_allowed": False,
        "p1_allowed": False,
        "require_allow_flag": True,
    },
}


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | Path | None = None) -> CompilerConfig:
    data = DEFAULT_CONFIG
    if path:
        loaded = yaml.safe_load(Path(path).read_text()) or {}
        data = deep_merge(DEFAULT_CONFIG, loaded)
    return CompilerConfig.model_validate(data)


def priority_ttl_attr(priority: str) -> str:
    return f"{priority.lower()}_max_ttl_minutes"

