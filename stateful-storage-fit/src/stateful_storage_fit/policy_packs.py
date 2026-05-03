from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import PolicyPack


class PolicyPackError(ValueError):
    pass


def load_policy_pack(path: Path | None) -> PolicyPack | None:
    if path is None:
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise PolicyPackError(f"policy pack YAML parse failed: {exc}") from exc
    if not isinstance(data, dict):
        raise PolicyPackError("policy pack must be a YAML mapping")
    try:
        return PolicyPack(**data)
    except ValidationError as exc:
        raise PolicyPackError(f"policy pack validation failed: {exc}") from exc


def apply_policy_pack(config: dict, policy_pack: PolicyPack | None) -> dict:
    merged = dict(config)
    if policy_pack is not None:
        merged.update(policy_pack.threshold_overrides)
    return merged

