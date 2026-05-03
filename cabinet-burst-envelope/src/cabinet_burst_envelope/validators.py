from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .cabinet_profile import load_cabinet_profile
from .models import CabinetProfile, PowerReading, TemperatureReading
from .normalize import add_unique, stable_unique
from .parse_power import parse_power_csv
from .parse_temperature import parse_temperature_csv
from .time_align import is_valid_inlet_sensor


@dataclass
class LoadedInputs:
    profile: CabinetProfile | None
    power_rows: list[PowerReading]
    temperature_rows: list[TemperatureReading]
    cabinet_id: str
    power_input_rows: int
    temperature_input_rows: int
    reason_codes: list[str]
    warnings: list[str]
    missing_data: list[str]


def load_and_validate_inputs(
    power_path: str | Path | None,
    temperature_path: str | Path | None,
    profile_path: str | Path | None,
    config: dict,
    strict: bool = False,
) -> LoadedInputs:
    profile, profile_result = load_cabinet_profile(profile_path, strict=strict)
    power_result = parse_power_csv(power_path, strict=strict)
    temperature_result = parse_temperature_csv(temperature_path, strict=strict, config=config)

    reason_codes = []
    warnings = []
    missing_data = []
    for result in (profile_result, power_result, temperature_result):
        for code in result.reason_codes:
            add_unique(reason_codes, code)
        for warning in result.warnings:
            add_unique(warnings, warning)
        for missing in result.missing_data:
            add_unique(missing_data, missing)

    all_ids = stable_unique(
        list(profile_result.cabinet_ids)
        + list(power_result.cabinet_ids)
        + list(temperature_result.cabinet_ids)
    )
    if profile is not None:
        cabinet_id = profile.cabinet_id
    elif power_result.cabinet_ids:
        cabinet_id = power_result.cabinet_ids[0]
    elif temperature_result.cabinet_ids:
        cabinet_id = temperature_result.cabinet_ids[0]
    else:
        cabinet_id = "unknown"

    if len(all_ids) > 1:
        add_unique(reason_codes, "MULTIPLE_CABINETS_IN_INPUT")
        add_unique(warnings, "MULTIPLE_CABINETS_IN_INPUT")
        if strict:
            raise ValueError("cabinet IDs do not match across inputs")

    power_rows = [row for row in power_result.rows if row.cabinet_id == cabinet_id]
    temperature_rows = [row for row in temperature_result.rows if row.cabinet_id == cabinet_id]
    if power_rows and all(row.reading_kw == 0 for row in power_rows):
        add_unique(reason_codes, "ALL_ZERO_POWER_READINGS")
        add_unique(warnings, "ALL_ZERO_POWER_READINGS")

    if strict:
        if not power_rows:
            raise ValueError("strict mode requires valid power rows for the selected cabinet")
        if not temperature_rows:
            raise ValueError("strict mode requires valid temperature rows for the selected cabinet")
        if profile is None:
            raise ValueError("strict mode requires a valid cabinet profile")
        if profile.electrical.usable_sustained_kw is None:
            raise ValueError("strict mode requires electrical.usable_sustained_kw")
        if profile.thermal.inlet_warning_c is None:
            raise ValueError("strict mode requires thermal.inlet_warning_c")
        if not any(is_valid_inlet_sensor(row) for row in temperature_rows):
            raise ValueError("strict mode requires at least one valid inlet sensor")
        if "PROFILE_INVALID" in missing_data:
            raise ValueError("strict mode requires a profile without contradictory limits")
        if "ALL_ZERO_POWER_READINGS" in warnings:
            raise ValueError("strict mode rejects all-zero power readings")

    return LoadedInputs(
        profile=profile,
        power_rows=power_rows,
        temperature_rows=temperature_rows,
        cabinet_id=cabinet_id,
        power_input_rows=power_result.input_rows,
        temperature_input_rows=temperature_result.input_rows,
        reason_codes=reason_codes,
        warnings=warnings,
        missing_data=missing_data,
    )
