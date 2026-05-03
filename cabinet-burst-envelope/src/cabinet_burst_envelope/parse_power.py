from __future__ import annotations

import csv
from pathlib import Path

from .models import ParseResult, PowerReading
from .normalize import (
    add_unique,
    lower_or_default,
    parse_optional_float,
    parse_required_float,
    parse_timestamp,
    stable_unique,
    text_or_none,
)


REQUIRED_COLUMNS = {"timestamp", "cabinet_id", "reading_kw"}


def parse_power_csv(path: str | Path | None, strict: bool = False) -> ParseResult:
    result = ParseResult()
    if path is None or not Path(path).exists():
        add_unique(result.reason_codes, "POWER_DATA_MISSING")
        add_unique(result.missing_data, "POWER_DATA_MISSING")
        if strict:
            raise ValueError("power CSV is required")
        return result

    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - fieldnames
        if missing:
            add_unique(result.reason_codes, "POWER_DATA_MISSING")
            if strict:
                raise ValueError(f"power CSV missing required columns: {', '.join(sorted(missing))}")
            return result

        for row_number, row in enumerate(reader, start=2):
            result.input_rows += 1
            quality = lower_or_default(row.get("reading_quality"), "good")
            if quality == "missing":
                continue
            try:
                timestamp, timezone_unknown = parse_timestamp(row.get("timestamp", ""))
                reading_kw = parse_required_float(row.get("reading_kw"), "reading_kw")
                if reading_kw < 0:
                    raise ValueError("reading_kw must be non-negative")
                cabinet_id = (row.get("cabinet_id") or "").strip()
                if not cabinet_id:
                    raise ValueError("cabinet_id is required")
                reading_scope = lower_or_default(row.get("reading_scope"), "unknown")
                reading = PowerReading(
                    timestamp=timestamp,
                    cabinet_id=cabinet_id,
                    reading_kw=reading_kw,
                    feed_id=text_or_none(row.get("feed_id")),
                    pdu_id=text_or_none(row.get("pdu_id")),
                    reading_scope=reading_scope,
                    source=text_or_none(row.get("source")),
                    phase=text_or_none(row.get("phase")),
                    circuit_id=text_or_none(row.get("circuit_id")),
                    voltage_v=parse_optional_float(row.get("voltage_v")),
                    current_a=parse_optional_float(row.get("current_a")),
                    apparent_power_kva=parse_optional_float(row.get("apparent_power_kva")),
                    power_factor=parse_optional_float(row.get("power_factor")),
                    outlet_id=text_or_none(row.get("outlet_id")),
                    reading_quality=quality,
                    source_row_id=text_or_none(row.get("source_row_id")) or str(row_number),
                    source_row_number=row_number,
                    timezone_unknown=timezone_unknown,
                )
            except Exception as exc:
                if strict:
                    raise ValueError(f"invalid power row {row_number}: {exc}") from exc
                add_unique(result.warnings, "POWER_DATA_MISSING")
                continue

            if reading.timezone_unknown:
                add_unique(result.reason_codes, "TIMESTAMP_TIMEZONE_UNKNOWN")
                add_unique(result.warnings, "TIMESTAMP_TIMEZONE_UNKNOWN")
            if reading.reading_scope == "unknown":
                add_unique(result.reason_codes, "READING_SCOPE_UNKNOWN")
                add_unique(result.warnings, "READING_SCOPE_UNKNOWN")
            if quality == "estimated":
                add_unique(result.reason_codes, "ESTIMATED_POWER_READINGS_PRESENT")
                add_unique(result.warnings, "ESTIMATED_POWER_READINGS_PRESENT")
            if quality == "stale":
                add_unique(result.reason_codes, "STALE_POWER_READINGS_PRESENT")
                add_unique(result.warnings, "STALE_POWER_READINGS_PRESENT")
            result.rows.append(reading)

    if result.rows:
        add_unique(result.reason_codes, "POWER_DATA_PRESENT")
    else:
        add_unique(result.reason_codes, "POWER_DATA_MISSING")
        add_unique(result.missing_data, "POWER_DATA_MISSING")
    result.cabinet_ids = stable_unique(reading.cabinet_id for reading in result.rows)
    if len(result.cabinet_ids) > 1:
        add_unique(result.reason_codes, "MULTIPLE_CABINETS_IN_INPUT")
        add_unique(result.warnings, "MULTIPLE_CABINETS_IN_INPUT")
        if strict:
            raise ValueError("power CSV contains multiple cabinet IDs")
    return result
