from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from cabinet_burst_envelope.config import DEFAULT_CONFIG


START = datetime(2025, 12, 25, tzinfo=timezone.utc)
NOW = "2026-01-01T00:00:00Z"
BUCKETS_7D = 7 * 24 * 12


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def base_profile(cabinet_id: str = "cab-test") -> dict:
    return {
        "cabinet_id": cabinet_id,
        "display_name": "Cabinet Test",
        "site_policy_id": "default-air-cooled",
        "electrical": {
            "usable_sustained_kw": 24.0,
            "usable_burst_kw": 28.0,
            "trip_risk_kw": 30.0,
            "redundancy_mode": "A_B_SHARED",
            "require_single_feed_survival": False,
            "feed_limits": [
                {"feed_id": "A", "usable_sustained_kw": 12.0, "trip_risk_kw": 15.0},
                {"feed_id": "B", "usable_sustained_kw": 12.0, "trip_risk_kw": 15.0},
            ],
        },
        "thermal": {
            "inlet_warning_c": 30.0,
            "inlet_critical_c": 34.0,
            "require_top_middle_bottom": True,
            "max_thermal_extrapolation_kw": 20.0,
            "thermal_model_required_for_burst": False,
        },
        "guardbands": {
            "power_headroom_pct": 10,
            "min_power_headroom_kw": 1.0,
            "temp_headroom_c": 2.0,
            "sustained_window_minutes": 60,
            "burst_window_minutes": 5,
            "max_burst_duration_minutes": 15,
        },
        "sales_policy": {
            "allow_sales_guardrail": True,
            "require_ops_review_above_kw": 20.0,
            "require_facility_review_above_kw": 24.0,
            "wording": "conservative",
        },
    }


def write_profile(tmp_path: Path, profile: dict | None = None) -> Path:
    path = tmp_path / "cabinet_profile.yml"
    path.write_text(yaml.safe_dump(profile or base_profile()), encoding="utf-8")
    return path


def write_power_rows(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "pdu_power.csv"
    fields = ["timestamp", "cabinet_id", "feed_id", "pdu_id", "reading_scope", "reading_kw", "source", "reading_quality", "source_row_id", "circuit_id"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, row in enumerate(rows, start=1):
            out = {field: "" for field in fields}
            out.update(row)
            out.setdefault("source_row_id", f"p{index}")
            writer.writerow(out)
    return path


def write_temperature_rows(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "inlet_temps.csv"
    fields = ["timestamp", "cabinet_id", "sensor_id", "position", "height", "sensor_role", "inlet_temp_c", "source", "reading_quality", "source_row_id"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, row in enumerate(rows, start=1):
            out = {field: "" for field in fields}
            out.update(row)
            out.setdefault("source_row_id", f"t{index}")
            writer.writerow(out)
    return path


def generated_power_rows(
    cabinet_id: str = "cab-test",
    count: int = BUCKETS_7D,
    scope: str = "feed_total",
    base_kw: float = 16.0,
    variation_kw: float = 3.0,
    every: int = 1,
    imbalance: float = 0.52,
    quality: str = "good",
) -> list[dict]:
    rows: list[dict] = []
    for i in range(count):
        if i % every != 0:
            continue
        ts = iso(START + timedelta(minutes=5 * i))
        total = base_kw + variation_kw * (i / max(1, count - 1))
        total += 0.25 * math.sin(2 * math.pi * (i % 288) / 288)
        if scope == "total_cabinet":
            rows.append({"timestamp": ts, "cabinet_id": cabinet_id, "reading_scope": "total_cabinet", "reading_kw": round(total, 3), "pdu_id": "pdu-main", "source": "normalized-power", "reading_quality": quality})
        else:
            a_kw = round(total * imbalance, 3)
            b_kw = round(total - a_kw, 3)
            rows.append({"timestamp": ts, "cabinet_id": cabinet_id, "feed_id": "A", "pdu_id": "pdu-a", "reading_scope": scope, "reading_kw": a_kw, "source": "normalized-power", "reading_quality": quality})
            rows.append({"timestamp": ts, "cabinet_id": cabinet_id, "feed_id": "B", "pdu_id": "pdu-b", "reading_scope": scope, "reading_kw": b_kw, "source": "normalized-power", "reading_quality": quality})
    return rows


def generated_temperature_rows(
    cabinet_id: str = "cab-test",
    count: int = BUCKETS_7D,
    base_kw: float = 16.0,
    variation_kw: float = 3.0,
    slope: float = 0.2,
    every: int = 1,
    include_top: bool = True,
    include_middle: bool = True,
    include_bottom: bool = True,
    top_delta: float = 1.0,
) -> list[dict]:
    rows: list[dict] = []
    for i in range(count):
        if i % every != 0:
            continue
        ts = iso(START + timedelta(minutes=5 * i))
        power = base_kw + variation_kw * (i / max(1, count - 1))
        top = 18.0 + slope * power
        sensors = []
        if include_top:
            sensors.append(("sensor-top", "front_top", "top", top + top_delta))
        if include_middle:
            sensors.append(("sensor-middle", "front_middle", "middle", top))
        if include_bottom:
            sensors.append(("sensor-bottom", "front_bottom", "bottom", top - 1.0))
        for sensor_id, position, height, temp in sensors:
            rows.append({"timestamp": ts, "cabinet_id": cabinet_id, "sensor_id": sensor_id, "position": position, "height": height, "sensor_role": "inlet", "inlet_temp_c": round(temp, 3), "source": "normalized-temperature", "reading_quality": "good"})
    return rows


@pytest.fixture
def default_config() -> dict:
    config = dict(DEFAULT_CONFIG)
    config["long_gap_minutes"] = 60
    return config
