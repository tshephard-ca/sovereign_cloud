from __future__ import annotations

import json
from pathlib import Path

from .config import ensure_parent
from .parse_bmc_snapshot import parse_bmc_snapshot


def import_bmc_snapshot(input_json: Path, output_json: Path) -> dict[str, object]:
    snapshot = parse_bmc_snapshot(input_json)
    normalized = {
        "schema_version": "rackq.normalized_bmc_snapshot.v1",
        "source": str(input_json),
        "parsed": snapshot.parsed,
        "warning_count": snapshot.warning_count,
        "critical_count": snapshot.critical_count,
        "fan_failure_count": snapshot.fan_failure_count,
        "temp_max_celsius": snapshot.temp_max_celsius,
        "reason_codes": snapshot.reason_codes,
        "sensors": [_sensor_dict(sensor) for sensor in snapshot.sensors],
    }
    ensure_parent(output_json)
    output_json.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return normalized


def _sensor_dict(sensor) -> dict[str, object]:
    if hasattr(sensor, "model_dump"):
        return sensor.model_dump()
    return sensor.dict()
