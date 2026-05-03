from __future__ import annotations

import csv
from pathlib import Path

from .config import DEFAULT_CONFIG
from .models import ParseResult, TemperatureReading
from .normalize import (
    add_unique,
    lower_or_default,
    parse_optional_float,
    parse_required_float,
    parse_timestamp,
    stable_unique,
    text_or_none,
)


REQUIRED_COLUMNS = {"timestamp", "cabinet_id", "sensor_id", "inlet_temp_c"}


def parse_temperature_csv(
    path: str | Path | None,
    strict: bool = False,
    config: dict | None = None,
) -> ParseResult:
    result = ParseResult()
    thresholds = config or DEFAULT_CONFIG
    if path is None or not Path(path).exists():
        add_unique(result.reason_codes, "TEMPERATURE_DATA_MISSING")
        add_unique(result.missing_data, "TEMPERATURE_DATA_MISSING")
        if strict:
            raise ValueError("temperature CSV is required")
        return result

    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - fieldnames
        if missing:
            add_unique(result.reason_codes, "TEMPERATURE_DATA_MISSING")
            if strict:
                raise ValueError(f"temperature CSV missing required columns: {', '.join(sorted(missing))}")
            return result

        for row_number, row in enumerate(reader, start=2):
            result.input_rows += 1
            quality = lower_or_default(row.get("reading_quality"), "good")
            if quality == "missing":
                continue
            try:
                timestamp, timezone_unknown = parse_timestamp(row.get("timestamp", ""))
                inlet_temp_c = parse_required_float(row.get("inlet_temp_c"), "inlet_temp_c")
                cabinet_id = (row.get("cabinet_id") or "").strip()
                sensor_id = (row.get("sensor_id") or "").strip()
                if not cabinet_id:
                    raise ValueError("cabinet_id is required")
                if not sensor_id:
                    raise ValueError("sensor_id is required")
                reading = TemperatureReading(
                    timestamp=timestamp,
                    cabinet_id=cabinet_id,
                    sensor_id=sensor_id,
                    inlet_temp_c=inlet_temp_c,
                    position=lower_or_default(row.get("position"), "unknown"),
                    height=lower_or_default(row.get("height"), "unknown"),
                    source=text_or_none(row.get("source")),
                    sensor_role=lower_or_default(row.get("sensor_role"), "unknown"),
                    reading_quality=quality,
                    humidity_pct=parse_optional_float(row.get("humidity_pct")),
                    dewpoint_c=parse_optional_float(row.get("dewpoint_c")),
                    source_row_id=text_or_none(row.get("source_row_id")) or str(row_number),
                    source_row_number=row_number,
                    timezone_unknown=timezone_unknown,
                )
            except Exception as exc:
                if strict:
                    raise ValueError(f"invalid temperature row {row_number}: {exc}") from exc
                add_unique(result.warnings, "TEMPERATURE_DATA_MISSING")
                continue

            if reading.timezone_unknown:
                add_unique(result.reason_codes, "TIMESTAMP_TIMEZONE_UNKNOWN")
                add_unique(result.warnings, "TIMESTAMP_TIMEZONE_UNKNOWN")
            if quality == "estimated":
                add_unique(result.reason_codes, "ESTIMATED_TEMPERATURE_READINGS_PRESENT")
                add_unique(result.warnings, "ESTIMATED_TEMPERATURE_READINGS_PRESENT")
            if quality == "stale":
                add_unique(result.reason_codes, "STALE_TEMPERATURE_READINGS_PRESENT")
                add_unique(result.warnings, "STALE_TEMPERATURE_READINGS_PRESENT")
            if reading.inlet_temp_c < thresholds["plausible_min_temp_c"] or reading.inlet_temp_c > thresholds["plausible_max_temp_c"]:
                add_unique(result.warnings, "TEMPERATURE_VALUE_OUTSIDE_PLAUSIBLE_RANGE")
            result.rows.append(reading)

    if result.rows:
        add_unique(result.reason_codes, "TEMPERATURE_DATA_PRESENT")
    else:
        add_unique(result.reason_codes, "TEMPERATURE_DATA_MISSING")
        add_unique(result.missing_data, "TEMPERATURE_DATA_MISSING")
    result.cabinet_ids = stable_unique(reading.cabinet_id for reading in result.rows)
    if len(result.cabinet_ids) > 1:
        add_unique(result.reason_codes, "MULTIPLE_CABINETS_IN_INPUT")
        add_unique(result.warnings, "MULTIPLE_CABINETS_IN_INPUT")
        if strict:
            raise ValueError("temperature CSV contains multiple cabinet IDs")
    return result
