from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import EndpointProfiles


def load_endpoint_profiles(path: str) -> EndpointProfiles:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return EndpointProfiles.model_validate(data)


def validate_endpoint_profiles(path: str) -> tuple[EndpointProfiles | None, list[str], list[str]]:
    try:
        endpoints = load_endpoint_profiles(path)
    except (OSError, ValidationError, yaml.YAMLError, ValueError) as exc:
        return None, [], [f"ENDPOINT_PROFILE_INVALID: {exc}"]
    return endpoints, [], []
