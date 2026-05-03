from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import PolicyPack, ValidationResult


DEFAULT_POLICY_PACK: dict[str, Any] = {
    "pack_id": "default",
    "description": "Default conservative brownout policy pack.",
    "ttl": {
        "default_minutes": 30,
        "p0_max_minutes": 30,
        "p1_max_minutes": 30,
        "p2_max_minutes": 20,
        "p3_max_minutes": 15,
        "p4_max_minutes": 15,
        "null_route_max_minutes": 10,
    },
    "rate_limit_profiles": {
        "protect_critical_udp": {
            "description": "Conservative untrusted UDP limit for critical services.",
            "abstract_rate": "low",
            "applies_to": ["udp"],
        },
        "public_web_low_priority": {
            "description": "Reduce low-priority public web traffic.",
            "abstract_rate": "medium",
            "applies_to": ["tcp"],
        },
    },
    "action_preferences": {
        "P0": ["ALLOW_TRUSTED_SOURCES", "PRIORITIZE", "RATE_LIMIT_UNTRUSTED"],
        "P1": ["ALLOW_TRUSTED_SOURCES", "PRIORITIZE", "RATE_LIMIT_UNTRUSTED"],
        "P2": ["RATE_LIMIT", "DEPRIORITIZE"],
        "P3": ["RATE_LIMIT", "SHED_LOW_PRIORITY"],
        "P4": ["SHED_LOW_PRIORITY", "RATE_LIMIT"],
    },
    "risk_defaults": {
        "TEMPORARY_NULL_ROUTE": "CRITICAL",
        "DENY_UNTRUSTED": "HIGH",
        "TEMPORARY_BLOCK_PORT": "HIGH",
        "RATE_LIMIT_UNTRUSTED": "MEDIUM",
        "RATE_LIMIT": "MEDIUM",
        "SHED_LOW_PRIORITY": "MEDIUM",
        "PRIORITIZE": "LOW",
        "ALLOW_TRUSTED_SOURCES": "LOW",
        "DEPRIORITIZE": "MEDIUM",
        "CHALLENGE": "MEDIUM",
        "MONITOR_ONLY": "LOW",
        "NO_ACTION": "LOW",
    },
}


def default_policy_pack() -> PolicyPack:
    return PolicyPack.model_validate(DEFAULT_POLICY_PACK)


def load_policy_pack(path: str | Path | None = None) -> tuple[PolicyPack | None, ValidationResult, bool]:
    result = ValidationResult()
    if path is None:
        result.warnings.append("POLICY_PACK_NOT_SUPPLIED_USING_DEFAULT")
        return default_policy_pack(), result, False
    try:
        data = yaml.safe_load(Path(path).read_text()) or {}
        return PolicyPack.model_validate(data), result, True
    except (ValidationError, ValueError, yaml.YAMLError) as exc:
        result.blockers.append("POLICY_PACK_INVALID")
        result.warnings.append(str(exc))
        return None, result, True

