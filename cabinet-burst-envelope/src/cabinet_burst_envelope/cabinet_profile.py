from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import CabinetProfile, ParseResult
from .normalize import add_unique


def validate_profile_contract(profile: CabinetProfile) -> tuple[list[str], list[str], list[str]]:
    reason_codes: list[str] = []
    warnings: list[str] = []
    missing_data: list[str] = []
    electrical = profile.electrical
    thermal = profile.thermal

    def invalid(code: str) -> None:
        add_unique(reason_codes, code, "PROFILE_INVALID")
        add_unique(warnings, code)
        add_unique(missing_data, "PROFILE_INVALID")

    if (
        electrical.usable_sustained_kw is not None
        and electrical.usable_burst_kw is not None
        and electrical.usable_burst_kw < electrical.usable_sustained_kw
    ):
        invalid("BURST_LIMIT_BELOW_SUSTAINED_LIMIT")
    if (
        electrical.trip_risk_kw is not None
        and electrical.usable_sustained_kw is not None
        and electrical.trip_risk_kw < electrical.usable_sustained_kw
    ):
        invalid("TRIP_THRESHOLD_BELOW_SUSTAINED_LIMIT")
    if (
        electrical.trip_risk_kw is not None
        and electrical.usable_burst_kw is not None
        and electrical.trip_risk_kw < electrical.usable_burst_kw
    ):
        invalid("TRIP_THRESHOLD_BELOW_BURST_LIMIT")
    if (
        thermal.inlet_warning_c is not None
        and thermal.inlet_critical_c is not None
        and thermal.inlet_critical_c < thermal.inlet_warning_c
    ):
        invalid("THERMAL_CRITICAL_BELOW_WARNING_LIMIT")
    if thermal.max_thermal_extrapolation_kw is not None and thermal.max_thermal_extrapolation_kw < 0:
        invalid("NEGATIVE_THERMAL_EXTRAPOLATION_LIMIT")
    for feed_limit in electrical.feed_limits:
        if feed_limit.usable_sustained_kw is not None and feed_limit.usable_sustained_kw < 0:
            invalid("NEGATIVE_FEED_LIMIT")
        if feed_limit.trip_risk_kw is not None and feed_limit.trip_risk_kw < 0:
            invalid("NEGATIVE_FEED_TRIP_THRESHOLD")
        if (
            feed_limit.usable_sustained_kw is not None
            and feed_limit.trip_risk_kw is not None
            and feed_limit.trip_risk_kw < feed_limit.usable_sustained_kw
        ):
            invalid("FEED_TRIP_THRESHOLD_BELOW_FEED_LIMIT")
    return reason_codes, warnings, missing_data


def load_cabinet_profile(path: str | Path | None, strict: bool = False) -> tuple[CabinetProfile | None, ParseResult]:
    result = ParseResult()
    if path is None or not Path(path).exists():
        add_unique(result.reason_codes, "CABINET_PROFILE_MISSING")
        add_unique(result.missing_data, "CABINET_PROFILE_MISSING")
        if strict:
            raise ValueError("cabinet profile is required")
        return None, result

    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        if not isinstance(loaded, dict):
            raise ValueError("cabinet profile must be a YAML mapping")
        profile = CabinetProfile.model_validate(loaded)
    except (OSError, ValidationError, ValueError) as exc:
        add_unique(result.reason_codes, "CABINET_PROFILE_MISSING")
        add_unique(result.missing_data, "PROFILE_INVALID")
        if strict:
            raise ValueError(f"invalid cabinet profile: {exc}") from exc
        return None, result

    add_unique(result.reason_codes, "CABINET_PROFILE_PRESENT")
    result.cabinet_ids = [profile.cabinet_id]
    profile_reasons, profile_warnings, profile_missing = validate_profile_contract(profile)
    for code in profile_reasons:
        add_unique(result.reason_codes, code)
    for code in profile_warnings:
        add_unique(result.warnings, code)
    for code in profile_missing:
        add_unique(result.missing_data, code)
    if strict and profile_missing:
        raise ValueError(f"invalid cabinet profile contract: {', '.join(profile_reasons)}")
    return profile, result
