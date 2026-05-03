from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import Constraints, DeclaredLocation


def load_constraints(path: str) -> Constraints:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Constraints.model_validate(data)


def validate_constraints(path: str) -> tuple[Constraints | None, list[str], list[str]]:
    try:
        constraints = load_constraints(path)
    except (OSError, ValidationError, yaml.YAMLError, ValueError) as exc:
        return None, [], [f"CONSTRAINTS_INVALID: {exc}"]
    return constraints, [], []


def declared_location_reason_codes(
    location: DeclaredLocation | None,
    constraints: Constraints,
) -> tuple[bool, list[str]]:
    rules = constraints.data_location
    codes: list[str] = []
    if location is None:
        if rules.require_declared_location:
            return False, ["DECLARED_LOCATION_MISSING"]
        return True, ["DECLARED_LOCATION_MISSING"]
    codes.append("DECLARED_LOCATION_PRESENT")

    allowed = True
    if rules.allowed_countries and location.country not in rules.allowed_countries:
        allowed = False
    if rules.allowed_regions and location.region not in rules.allowed_regions:
        allowed = False
    if rules.allowed_data_zones and location.data_zone not in rules.allowed_data_zones:
        allowed = False
    if allowed:
        codes.append("DECLARED_LOCATION_ALLOWED")
    else:
        codes.append("DECLARED_LOCATION_NOT_ALLOWED")

    operator_allowed = True
    if rules.allowed_operator_control and location.operator_control not in rules.allowed_operator_control:
        operator_allowed = False
    codes.append("OPERATOR_CONTROL_ALLOWED" if operator_allowed else "OPERATOR_CONTROL_NOT_ALLOWED")
    return allowed and operator_allowed, codes
