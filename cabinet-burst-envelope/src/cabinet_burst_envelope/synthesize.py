from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from .config import DEFAULT_CONFIG
from .models import ScenarioManifest
from .normalize import isoformat_z
from .report import write_json


SYNTHETIC_NOW = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class ScenarioControls:
    base_kw: float = 16.0
    variation_kw: float = 3.0
    burst_kw: float = 3.0
    burst_frequency: int = 431
    burst_duration_buckets: int = 3
    power_daily_kw: float = 0.25
    thermal_slope: float = 0.20
    thermal_lag_minutes: int = 0
    noise: float = 0.03
    missing_power_pct: float = 0.0
    missing_temp_pct: float = 0.0
    sensor_set: tuple[str, ...] = ("top", "middle", "bottom")
    feed_imbalance_pct: float = 4.0
    reading_scope: str = "feed_total"
    power_quality: str = "good"
    temp_quality: str = "good"
    top_delta_c: float = 1.0
    naive_timestamps: bool = False
    multiple_cabinet_ids: bool = False
    ambient_only: bool = False
    electrical_sustained_kw: float | None = 24.0
    electrical_burst_kw: float | None = 28.0
    trip_risk_kw: float | None = 30.0
    thermal_warning_c: float | None = 30.0
    thermal_critical_c: float | None = 34.0
    max_thermal_extrapolation_kw: float = 20.0
    redundancy_mode: str = "A_B_SHARED"
    require_single_feed_survival: bool = False
    workload_pattern: str = "steady_ramp"
    sample_every_buckets: int = 1
    timestamp_jitter_seconds: int = 0
    out_of_order_rows: bool = False
    duplicate_power_every: int = 0
    duplicate_temp_every: int = 0
    populate_electrical_detail: bool = False
    include_humidity_dewpoint: bool = False
    profile_family: str = "air_cooled"
    annotation_event: str | None = None
    expected: dict[str, Any] = field(default_factory=dict)


SCENARIOS: dict[str, ScenarioControls] = {
    "healthy_margin": ScenarioControls(
        max_thermal_extrapolation_kw=100.0,
        expected={
            "envelope_status": "READY_FOR_REVIEW",
            "confidence": "HIGH",
            "limiting_factor": "ELECTRICAL",
            "recommended_sustained_kw_range": [21.5, 21.6],
            "recommended_short_burst_kw_range": [25.5, 25.6],
        },
    ),
    "electrical_limited": ScenarioControls(electrical_sustained_kw=19.0, electrical_burst_kw=22.0, expected={"limiting_factor": "ELECTRICAL"}),
    "thermal_limited": ScenarioControls(thermal_slope=0.55, thermal_warning_c=29.0, thermal_critical_c=32.0, max_thermal_extrapolation_kw=40.0, expected={"limiting_factor": "THERMAL"}),
    "burst_near_trip_threshold": ScenarioControls(base_kw=20.0, variation_kw=1.0, burst_kw=8.0, burst_frequency=50, trip_risk_kw=30.5, expected={"reason_codes": ["MEDIUM_TRIP_RISK"]}),
    "current_load_exceeds_guardrail": ScenarioControls(base_kw=20.0, variation_kw=2.0, electrical_sustained_kw=18.0, electrical_burst_kw=20.0, expected={"envelope_status": "DO_NOT_EXPAND", "blockers": ["CURRENT_SUSTAINED_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL", "CURRENT_BURST_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL"]}),
    "all_zero_power": ScenarioControls(
        base_kw=0.0,
        variation_kw=0.0,
        burst_kw=0.0,
        power_daily_kw=0.0,
        noise=0.0,
        expected={"envelope_status": "INSUFFICIENT_DATA", "blockers": ["ALL_ZERO_POWER_READINGS"]},
    ),
    "top_inlet_hotspot": ScenarioControls(top_delta_c=6.0, expected={"reason_codes": ["HOTSPOT_TOP_INLET"]}),
    "thermal_creep": ScenarioControls(workload_pattern="thermal_creep", thermal_slope=0.26, thermal_warning_c=29.0, max_thermal_extrapolation_kw=40.0, expected={"limiting_factor": "THERMAL"}),
    "cooling_state_change": ScenarioControls(workload_pattern="cooling_step", annotation_event="cooling_state_change", thermal_slope=0.28, thermal_warning_c=29.0, expected={"limiting_factor": "THERMAL"}),
    "neighbor_heat_event": ScenarioControls(workload_pattern="neighbor_heat", annotation_event="neighbor_heat_event", top_delta_c=2.5, expected={"reason_codes": ["HOTSPOT_TOP_INLET"]}),
    "sensor_drift": ScenarioControls(workload_pattern="sensor_drift", top_delta_c=1.5, expected={"reason_codes": ["HOTSPOT_TOP_INLET"]}),
    "missing_top_sensor": ScenarioControls(sensor_set=("middle", "bottom"), expected={"missing_data": ["MISSING_TOP_INLET_SENSOR"]}),
    "missing_middle_sensor": ScenarioControls(sensor_set=("top", "bottom"), expected={"missing_data": ["MISSING_MIDDLE_INLET_SENSOR"]}),
    "missing_bottom_sensor": ScenarioControls(sensor_set=("top", "middle"), expected={"missing_data": ["MISSING_BOTTOM_INLET_SENSOR"]}),
    "ambient_only": ScenarioControls(ambient_only=True, sensor_set=(), expected={"envelope_status": "INSUFFICIENT_DATA", "missing_data": ["NO_VALID_INLET_SENSOR"], "blockers": ["NO_VALID_INLET_SENSOR"]}),
    "low_power_variation": ScenarioControls(variation_kw=0.2, burst_kw=0.0, expected={"reason_codes": ["POWER_VARIATION_TOO_LOW_FOR_THERMAL_MODEL"]}),
    "low_temperature_variation": ScenarioControls(thermal_slope=0.01, expected={"reason_codes": ["TEMP_VARIATION_TOO_LOW_FOR_THERMAL_MODEL"]}),
    "negative_thermal_slope": ScenarioControls(thermal_slope=-0.12, expected={"reason_codes": ["THERMAL_SLOPE_NOT_POSITIVE"]}),
    "low_coverage": ScenarioControls(missing_power_pct=0.55, missing_temp_pct=0.55, expected={"envelope_status": "INSUFFICIENT_DATA", "blockers": ["ALIGNED_COVERAGE_TOO_LOW"]}),
    "long_telemetry_gaps": ScenarioControls(missing_power_pct=0.0, missing_temp_pct=0.0, expected={"reason_codes": ["LONG_POWER_GAP", "LONG_TEMPERATURE_GAP"]}),
    "stale_readings": ScenarioControls(power_quality="stale", temp_quality="stale", expected={"warnings": ["STALE_POWER_READINGS_PRESENT", "STALE_TEMPERATURE_READINGS_PRESENT"]}),
    "estimated_readings": ScenarioControls(power_quality="estimated", temp_quality="estimated", expected={"warnings": ["ESTIMATED_POWER_READINGS_PRESENT", "ESTIMATED_TEMPERATURE_READINGS_PRESENT"]}),
    "unknown_reading_scope": ScenarioControls(reading_scope="unknown", expected={"warnings": ["READING_SCOPE_UNKNOWN"]}),
    "total_cabinet": ScenarioControls(reading_scope="total_cabinet", expected={"reason_codes": ["POWER_DATA_PRESENT"]}),
    "feed_total": ScenarioControls(reading_scope="feed_total", expected={"reason_codes": ["POWER_DATA_PRESENT"]}),
    "outlet": ScenarioControls(reading_scope="outlet", expected={"reason_codes": ["POWER_DATA_PRESENT"]}),
    "feed_imbalance_warning": ScenarioControls(feed_imbalance_pct=12.5, expected={"reason_codes": ["FEED_IMBALANCE_WARNING"]}),
    "feed_imbalance_critical": ScenarioControls(feed_imbalance_pct=45.0, expected={"envelope_status": "DO_NOT_EXPAND", "reason_codes": ["FEED_IMBALANCE_CRITICAL"], "blockers": ["FEED_IMBALANCE_CRITICAL"]}),
    "redundant_feed_survival_risk": ScenarioControls(base_kw=14.0, variation_kw=2.0, redundancy_mode="A_B_REDUNDANT", require_single_feed_survival=True, expected={"reason_codes": ["SINGLE_FEED_SURVIVAL_RISK"]}),
    "naive_timestamps": ScenarioControls(naive_timestamps=True, expected={"warnings": ["TIMESTAMP_TIMEZONE_UNKNOWN"]}),
    "multiple_cabinet_ids": ScenarioControls(multiple_cabinet_ids=True, expected={"warnings": ["MULTIPLE_CABINETS_IN_INPUT"]}),
    "weekday_weekend_cycle": ScenarioControls(workload_pattern="weekday_weekend", expected={"reason_codes": ["POWER_DATA_PRESENT"]}),
    "burst_heavy_workload": ScenarioControls(base_kw=14.0, variation_kw=1.5, burst_kw=9.0, burst_frequency=37, burst_duration_buckets=2, workload_pattern="burst_heavy", expected={"reason_codes": ["POWER_DATA_PRESENT"]}),
    "maintenance_window": ScenarioControls(workload_pattern="maintenance_window", annotation_event="maintenance_window", expected={"reason_codes": ["POWER_DATA_PRESENT"]}),
    "timestamp_jitter": ScenarioControls(timestamp_jitter_seconds=45, expected={"reason_codes": ["POWER_DATA_PRESENT"]}),
    "out_of_order_rows": ScenarioControls(out_of_order_rows=True, expected={"reason_codes": ["POWER_DATA_PRESENT"]}),
    "duplicate_readings": ScenarioControls(duplicate_power_every=113, duplicate_temp_every=127, expected={"reason_codes": ["POWER_DATA_PRESENT"]}),
    "ten_minute_cadence": ScenarioControls(sample_every_buckets=2, expected={"warnings": ["POWER_COVERAGE_LOW", "TEMPERATURE_COVERAGE_LOW", "ALIGNED_COVERAGE_LOW"]}),
    "rich_optional_fields": ScenarioControls(populate_electrical_detail=True, include_humidity_dewpoint=True, expected={"reason_codes": ["POWER_DATA_PRESENT"]}),
    "high_density_air_cooled": ScenarioControls(base_kw=24.0, variation_kw=4.0, electrical_sustained_kw=32.0, electrical_burst_kw=36.0, trip_risk_kw=40.0, thermal_warning_c=29.0, thermal_critical_c=33.0, thermal_slope=0.18, profile_family="high_density_air_cooled", expected={"reason_codes": ["POWER_DATA_PRESENT"]}),
    "liquid_cooled_profile": ScenarioControls(base_kw=28.0, variation_kw=5.0, electrical_sustained_kw=42.0, electrical_burst_kw=48.0, trip_risk_kw=52.0, thermal_warning_c=31.0, thermal_critical_c=36.0, thermal_slope=0.08, max_thermal_extrapolation_kw=60.0, profile_family="liquid_cooled", expected={"reason_codes": ["POWER_DATA_PRESENT"]}),
    "hybrid_cooling_profile": ScenarioControls(base_kw=22.0, variation_kw=5.0, electrical_sustained_kw=36.0, electrical_burst_kw=42.0, trip_risk_kw=46.0, thermal_warning_c=30.0, thermal_critical_c=35.0, thermal_slope=0.12, max_thermal_extrapolation_kw=50.0, profile_family="hybrid_air_liquid", expected={"reason_codes": ["POWER_DATA_PRESENT"]}),
    "missing_electrical_limits": ScenarioControls(electrical_sustained_kw=None, electrical_burst_kw=None, trip_risk_kw=None, expected={"reason_codes": ["ELECTRICAL_LIMIT_MISSING"]}),
    "missing_thermal_limits": ScenarioControls(thermal_warning_c=None, thermal_critical_c=None, expected={"reason_codes": ["THERMAL_LIMIT_MISSING"]}),
    "burst_limit_below_sustained": ScenarioControls(electrical_sustained_kw=24.0, electrical_burst_kw=20.0, expected={"envelope_status": "INSUFFICIENT_DATA", "confidence": "LOW", "reason_codes": ["BURST_LIMIT_BELOW_SUSTAINED_LIMIT"], "blockers": ["PROFILE_INVALID"]}),
    "thermal_critical_below_warning": ScenarioControls(thermal_warning_c=30.0, thermal_critical_c=28.0, expected={"envelope_status": "INSUFFICIENT_DATA", "confidence": "LOW", "reason_codes": ["THERMAL_CRITICAL_BELOW_WARNING_LIMIT"], "blockers": ["PROFILE_INVALID"]}),
    "trip_threshold_below_limit": ScenarioControls(trip_risk_kw=20.0, expected={"envelope_status": "INSUFFICIENT_DATA", "confidence": "LOW", "reason_codes": ["TRIP_THRESHOLD_BELOW_SUSTAINED_LIMIT", "TRIP_THRESHOLD_BELOW_BURST_LIMIT"], "blockers": ["PROFILE_INVALID"]}),
}


def list_scenarios() -> list[str]:
    return sorted(SCENARIOS)


def _profile(cabinet_id: str, controls: ScenarioControls) -> dict[str, Any]:
    electrical: dict[str, Any] = {
        "redundancy_mode": controls.redundancy_mode,
        "require_single_feed_survival": controls.require_single_feed_survival,
        "feed_limits": [
            {"feed_id": "A", "usable_sustained_kw": 12.0, "trip_risk_kw": 15.0},
            {"feed_id": "B", "usable_sustained_kw": 12.0, "trip_risk_kw": 15.0},
        ],
    }
    if controls.electrical_sustained_kw is not None:
        electrical["usable_sustained_kw"] = controls.electrical_sustained_kw
    if controls.electrical_burst_kw is not None:
        electrical["usable_burst_kw"] = controls.electrical_burst_kw
    if controls.trip_risk_kw is not None:
        electrical["trip_risk_kw"] = controls.trip_risk_kw

    thermal: dict[str, Any] = {
        "require_top_middle_bottom": True,
        "max_thermal_extrapolation_kw": controls.max_thermal_extrapolation_kw,
        "thermal_model_required_for_burst": False,
    }
    if controls.thermal_warning_c is not None:
        thermal["inlet_warning_c"] = controls.thermal_warning_c
    if controls.thermal_critical_c is not None:
        thermal["inlet_critical_c"] = controls.thermal_critical_c

    return {
        "cabinet_id": cabinet_id,
        "display_name": f"Cabinet {cabinet_id}",
        "site_policy_id": "synthetic-policy",
        "workload_label": controls.profile_family,
        "electrical": electrical,
        "thermal": thermal,
        "cooling_profile": {
            "family": controls.profile_family,
            "source": "synthetic-offline-annotation",
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


def _timestamp(value: datetime, naive: bool) -> str:
    text = isoformat_z(value)
    return text.replace("Z", "") if naive else text


def _jittered_timestamp(start: datetime, index: int, bucket_minutes: int, controls: ScenarioControls, rng: random.Random) -> str:
    value = start + timedelta(minutes=index * bucket_minutes)
    if controls.timestamp_jitter_seconds:
        jitter = rng.randint(-controls.timestamp_jitter_seconds, controls.timestamp_jitter_seconds)
        value += timedelta(seconds=jitter)
    return _timestamp(value, controls.naive_timestamps)


def _within(index: int, start_fraction: float, end_fraction: float, total_buckets: int) -> bool:
    return int(total_buckets * start_fraction) <= index < int(total_buckets * end_fraction)


def _power_for(index: int, total_buckets: int, controls: ScenarioControls, rng: random.Random) -> float:
    trend = controls.variation_kw * index / max(1, total_buckets - 1)
    daily = math.sin(2 * math.pi * (index % 288) / 288)
    burst = controls.burst_kw if controls.burst_frequency > 0 and index % controls.burst_frequency < controls.burst_duration_buckets else 0.0
    noise = rng.uniform(-controls.noise, controls.noise) if controls.noise else 0.0
    pattern_adjustment = 0.0
    day_index = index // 288
    if controls.workload_pattern == "weekday_weekend" and day_index in {2, 3}:
        pattern_adjustment -= min(controls.base_kw * 0.18, 4.0)
    elif controls.workload_pattern == "maintenance_window" and _within(index, 0.42, 0.48, total_buckets):
        pattern_adjustment -= min(controls.base_kw * 0.45, 8.0)
    elif controls.workload_pattern == "burst_heavy":
        burst += controls.burst_kw * 0.5 if index % 19 < 1 else 0.0
    return max(0.0, controls.base_kw + trend + controls.power_daily_kw * daily + burst + pattern_adjustment + noise)


def _missing(index: int, pct: float, rng: random.Random) -> bool:
    if pct <= 0:
        return False
    return rng.random() < pct


def _electrical_detail(reading_kw: float, phase: str | None = None) -> dict[str, Any]:
    power_factor = 0.96
    voltage = 240.0 if phase else 415.0
    current = reading_kw * 1000.0 / max(voltage * power_factor, 1.0)
    return {
        "phase": phase or "",
        "voltage_v": round(voltage, 1),
        "current_a": round(current, 3),
        "apparent_power_kva": round(reading_kw / power_factor, 3),
        "power_factor": power_factor,
    }


def _reorder_rows(rows: list[dict[str, Any]], enabled: bool) -> list[dict[str, Any]]:
    if not enabled:
        return rows
    out = list(rows)
    for index in range(20, len(out) - 1, 97):
        out[index], out[index + 1] = out[index + 1], out[index]
    return out


def _write_power(path: Path, cabinet_id: str, controls: ScenarioControls, days: int, bucket_minutes: int, seed: int) -> None:
    rng = random.Random(seed)
    total_buckets = days * 24 * 60 // bucket_minutes
    start = SYNTHETIC_NOW - timedelta(days=days)
    fields = [
        "timestamp",
        "cabinet_id",
        "feed_id",
        "pdu_id",
        "reading_scope",
        "reading_kw",
        "source",
        "reading_quality",
        "source_row_id",
        "outlet_id",
        "circuit_id",
        "phase",
        "voltage_v",
        "current_a",
        "apparent_power_kva",
        "power_factor",
    ]
    rows: list[dict[str, Any]] = []
    row_id = 1
    for index in range(total_buckets):
        if index % max(1, controls.sample_every_buckets) != 0:
            continue
        if _missing(index, controls.missing_power_pct, rng):
            continue
        if controls.scenario_name == "long_telemetry_gaps" and 20 <= index < 50:
            continue
        timestamp = _jittered_timestamp(start, index, bucket_minutes, controls, rng)
        total_kw = round(_power_for(index, total_buckets, controls, rng), 3)
        cabinet = "cabinet-other" if controls.multiple_cabinet_ids and index == total_buckets // 2 else cabinet_id
        if controls.reading_scope == "feed_total":
            a_fraction = 0.5 + controls.feed_imbalance_pct / 200.0
            feed_rows = [("A", total_kw * a_fraction), ("B", total_kw * (1.0 - a_fraction))]
            for feed_id, reading_kw in feed_rows:
                row = {
                    "timestamp": timestamp,
                    "cabinet_id": cabinet,
                    "feed_id": feed_id,
                    "pdu_id": f"pdu-{feed_id.lower()}",
                    "reading_scope": "feed_total",
                    "reading_kw": round(reading_kw, 3),
                    "source": "synthetic-power",
                    "reading_quality": controls.power_quality,
                    "source_row_id": f"p{row_id}",
                    "outlet_id": "",
                    "circuit_id": f"circuit-{feed_id.lower()}",
                }
                if controls.populate_electrical_detail:
                    row.update(_electrical_detail(float(row["reading_kw"]), phase="aggregate"))
                rows.append(row)
                row_id += 1
        elif controls.reading_scope == "outlet":
            for outlet in range(1, 5):
                row = {
                    "timestamp": timestamp,
                    "cabinet_id": cabinet,
                    "feed_id": "A" if outlet in {1, 2} else "B",
                    "pdu_id": "pdu-a" if outlet in {1, 2} else "pdu-b",
                    "reading_scope": "outlet",
                    "reading_kw": round(total_kw / 4.0, 3),
                    "source": "synthetic-power",
                    "reading_quality": controls.power_quality,
                    "source_row_id": f"p{row_id}",
                    "outlet_id": f"outlet-{outlet:02d}",
                    "circuit_id": f"circuit-{outlet:02d}",
                }
                if controls.populate_electrical_detail:
                    row.update(_electrical_detail(float(row["reading_kw"]), phase=["L1", "L2", "L3", "L1"][outlet - 1]))
                rows.append(row)
                row_id += 1
        else:
            row = {
                "timestamp": timestamp,
                "cabinet_id": cabinet,
                "feed_id": "",
                "pdu_id": "pdu-main",
                "reading_scope": controls.reading_scope,
                "reading_kw": total_kw,
                "source": "synthetic-power",
                "reading_quality": controls.power_quality,
                "source_row_id": f"p{row_id}",
                "outlet_id": "",
                "circuit_id": "circuit-main",
            }
            if controls.populate_electrical_detail:
                row.update(_electrical_detail(total_kw))
            rows.append(row)
            row_id += 1
        if controls.duplicate_power_every and index > 0 and index % controls.duplicate_power_every == 0:
            duplicates = [dict(row) for row in rows[-2:]]
            for duplicate in duplicates:
                duplicate["source_row_id"] = f"p{row_id}"
                duplicate["reading_kw"] = round(float(duplicate["reading_kw"]) * 1.002, 3)
                rows.append(duplicate)
                row_id += 1
    rows = _reorder_rows(rows, controls.out_of_order_rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _write_temperature(path: Path, cabinet_id: str, controls: ScenarioControls, days: int, bucket_minutes: int, seed: int) -> None:
    rng = random.Random(seed + 100_000)
    power_rng = random.Random(seed)
    total_buckets = days * 24 * 60 // bucket_minutes
    start = SYNTHETIC_NOW - timedelta(days=days)
    lag_buckets = max(0, controls.thermal_lag_minutes // bucket_minutes)
    power_series = [_power_for(index, total_buckets, controls, power_rng) for index in range(total_buckets)]
    fields = [
        "timestamp",
        "cabinet_id",
        "sensor_id",
        "position",
        "height",
        "sensor_role",
        "inlet_temp_c",
        "source",
        "reading_quality",
        "source_row_id",
        "humidity_pct",
        "dewpoint_c",
    ]
    rows: list[dict[str, Any]] = []
    row_id = 1
    for index in range(total_buckets):
        if index % max(1, controls.sample_every_buckets) != 0:
            continue
        if _missing(index, controls.missing_temp_pct, rng):
            continue
        if controls.scenario_name == "long_telemetry_gaps" and 100 <= index < 130:
            continue
        timestamp = _jittered_timestamp(start, index, bucket_minutes, controls, rng)
        lagged_power = power_series[max(0, index - lag_buckets)]
        daily = 0.15 * math.sin(2 * math.pi * ((index + 40) % 288) / 288)
        base_temp = 18.0 + controls.thermal_slope * lagged_power + daily
        if controls.workload_pattern == "thermal_creep":
            base_temp += 2.0 * index / max(1, total_buckets - 1)
        elif controls.workload_pattern == "cooling_step" and index >= total_buckets // 2:
            base_temp += 2.4
        elif controls.workload_pattern == "neighbor_heat" and _within(index, 0.55, 0.62, total_buckets):
            base_temp += 1.0
        elif controls.workload_pattern == "maintenance_window" and _within(index, 0.42, 0.48, total_buckets):
            base_temp -= 1.0
        cabinet = "cabinet-other" if controls.multiple_cabinet_ids and index == total_buckets // 2 else cabinet_id
        if controls.ambient_only:
            sensors = [("sensor-ambient", "ambient", "unknown", "ambient", base_temp - 1.0)]
        else:
            sensors = []
            drift = 2.0 * index / max(1, total_buckets - 1) if controls.workload_pattern == "sensor_drift" else 0.0
            neighbor_top = 3.0 if controls.workload_pattern == "neighbor_heat" and _within(index, 0.55, 0.62, total_buckets) else 0.0
            if "top" in controls.sensor_set:
                sensors.append(("sensor-top", "front_top", "top", "inlet", base_temp + controls.top_delta_c + drift + neighbor_top))
            if "middle" in controls.sensor_set:
                sensors.append(("sensor-middle", "front_middle", "middle", "inlet", base_temp + neighbor_top * 0.35))
            if "bottom" in controls.sensor_set:
                sensors.append(("sensor-bottom", "front_bottom", "bottom", "inlet", base_temp - 1.0))
        for sensor_id, position, height, role, temp_c in sensors:
            row = {
                "timestamp": timestamp,
                "cabinet_id": cabinet,
                "sensor_id": sensor_id,
                "position": position,
                "height": height,
                "sensor_role": role,
                "inlet_temp_c": round(temp_c, 3),
                "source": "synthetic-temperature",
                "reading_quality": controls.temp_quality,
                "source_row_id": f"t{row_id}",
            }
            if controls.include_humidity_dewpoint:
                humidity = 44.0 + 5.0 * math.sin(2 * math.pi * ((index + 80) % 288) / 288)
                row["humidity_pct"] = round(humidity, 2)
                row["dewpoint_c"] = round(temp_c - (100.0 - humidity) / 5.0, 3)
            rows.append(row)
            row_id += 1
        if controls.duplicate_temp_every and index > 0 and index % controls.duplicate_temp_every == 0:
            duplicates = [dict(row) for row in rows[-len(sensors) :]]
            for duplicate in duplicates:
                duplicate["source_row_id"] = f"t{row_id}"
                duplicate["inlet_temp_c"] = round(float(duplicate["inlet_temp_c"]) + 0.03, 3)
                rows.append(duplicate)
                row_id += 1
    rows = _reorder_rows(rows, controls.out_of_order_rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _write_annotations(path: Path, cabinet_id: str, controls: ScenarioControls, days: int) -> bool:
    if not controls.annotation_event:
        return False
    start = SYNTHETIC_NOW - timedelta(days=days)
    fields = ["timestamp", "cabinet_id", "annotation_type", "description", "source"]
    rows = [
        {
            "timestamp": isoformat_z(start + timedelta(days=days * 0.42)),
            "cabinet_id": cabinet_id,
            "annotation_type": controls.annotation_event,
            "description": {
                "maintenance_window": "Offline maintenance annotation for reduced load and inlet-temperature change.",
                "cooling_state_change": "Offline cooling-state annotation for step change in observed inlet temperature.",
                "neighbor_heat_event": "Offline neighboring-cabinet heat annotation for temporary top-inlet hot spot.",
            }.get(controls.annotation_event, "Offline synthetic annotation."),
            "source": "synthetic-annotation",
        }
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return True


def _expected_review_lane(scenario: str, controls: ScenarioControls) -> str:
    status = controls.expected.get("envelope_status")
    if status == "READY_FOR_REVIEW":
        return "READY_FOR_FACILITY_REVIEW"
    if status == "DO_NOT_EXPAND":
        return "STOP_EXPANSION_DISCUSSION"
    if status == "INSUFFICIENT_DATA":
        return "COLLECT_EVIDENCE"
    if any(token in scenario for token in ("missing", "coverage", "sensor", "timestamp", "stale", "estimated", "unknown", "zero")):
        return "COLLECT_EVIDENCE"
    if any(token in scenario for token in ("thermal", "hotspot", "cooling", "neighbor", "feed", "trip", "electrical")):
        return "NEEDS_REMEDIATION"
    return "NEEDS_REMEDIATION"


def _case_manifest(scenario: str, cabinet_id: str, controls: ScenarioControls) -> dict[str, Any]:
    lane = _expected_review_lane(scenario, controls)
    scenario_text = {
        "READY_FOR_FACILITY_REVIEW": "clean cabinet prequalification for facility review",
        "NEEDS_REMEDIATION": "risk signal needs remediation before the cabinet is treated as ready",
        "STOP_EXPANSION_DISCUSSION": "hard blocker or stop condition should stop the expansion discussion until remediated",
        "COLLECT_EVIDENCE": "missing or weak evidence must be corrected before capacity discussion",
    }[lane]
    return {
        "schema_version": "cabinet-burst-envelope.case_manifest.v1",
        "cabinet_id": cabinet_id,
        "case_goal": "assign a cabinet review lane from normalized local evidence",
        "business_scenario": scenario_text,
        "expected_review_lane": lane,
        "review_owner": "facility_engineering",
        "remediation_owner": "operations" if lane == "COLLECT_EVIDENCE" else "facility_engineering",
        "do_not_claim": [
            "facility approval",
            "reserved capacity",
            "customer commitment",
            "quote",
            "operational change",
        ],
        "synthetic_scenario": scenario,
        "controls_summary": {
            "profile_family": controls.profile_family,
            "reading_scope": controls.reading_scope,
            "base_kw": controls.base_kw,
            "variation_kw": controls.variation_kw,
            "thermal_slope": controls.thermal_slope,
            "feed_imbalance_pct": controls.feed_imbalance_pct,
        },
    }


def _controls_for(scenario: str, overrides: dict[str, Any]) -> ScenarioControls:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown synthetic scenario: {scenario}")
    base = SCENARIOS[scenario]
    values = dict(base.__dict__)
    values.pop("expected", None)
    values.update({key: value for key, value in overrides.items() if value is not None})
    controls = ScenarioControls(**values, expected=base.expected)
    object.__setattr__(controls, "scenario_name", scenario)
    return controls


def generate_scenario(
    output_dir: str | Path,
    scenario: str,
    cabinet_id: str | None = None,
    days: int = 7,
    bucket_minutes: int = 5,
    seed: int = 1,
    overrides: dict[str, Any] | None = None,
) -> ScenarioManifest:
    controls = _controls_for(scenario, overrides or {})
    cabinet = cabinet_id or f"cab-{scenario.replace('_', '-')}"
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)

    power_path = root / "pdu_power.csv"
    temp_path = root / "inlet_temps.csv"
    profile_path = root / "cabinet_profile.yml"
    thresholds_path = root / "thresholds.yml"
    expected_path = root / "expected_envelope.json"
    annotations_path = root / "annotations.csv"
    manifest_path = root / "scenario_manifest.yml"
    case_manifest_path = root / "case_manifest.yml"

    _write_power(power_path, cabinet, controls, days, bucket_minutes, seed)
    _write_temperature(temp_path, cabinet, controls, days, bucket_minutes, seed)
    wrote_annotations = _write_annotations(annotations_path, cabinet, controls, days)
    profile_path.write_text(yaml.safe_dump(_profile(cabinet, controls), sort_keys=False), encoding="utf-8")
    thresholds_path.write_text(yaml.safe_dump(DEFAULT_CONFIG, sort_keys=False), encoding="utf-8")
    case_manifest_path.write_text(yaml.safe_dump(_case_manifest(scenario, cabinet, controls), sort_keys=False), encoding="utf-8")
    write_json(expected_path, controls.expected)

    manifest = ScenarioManifest(
        scenario=scenario,
        cabinet_id=cabinet,
        generated_at=SYNTHETIC_NOW,
        days=days,
        bucket_minutes=bucket_minutes,
        seed=seed,
        files={
            "power": "pdu_power.csv",
            "temperature": "inlet_temps.csv",
            "cabinet_profile": "cabinet_profile.yml",
            "thresholds": "thresholds.yml",
            "case_manifest": "case_manifest.yml",
            "expected_envelope": "expected_envelope.json",
            **({"annotations": "annotations.csv"} if wrote_annotations else {}),
        },
        expected=controls.expected,
        controls={
            key: value
            for key, value in controls.__dict__.items()
            if key not in {"expected", "scenario_name"}
        },
    )
    manifest_path.write_text(yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
    return manifest


def generate_all_scenarios(
    output_dir: str | Path,
    days: int = 7,
    bucket_minutes: int = 5,
    seed: int = 1,
) -> list[ScenarioManifest]:
    root = Path(output_dir)
    manifests: list[ScenarioManifest] = []
    for index, scenario in enumerate(list_scenarios(), start=1):
        manifests.append(
            generate_scenario(
                root / scenario,
                scenario,
                days=days,
                bucket_minutes=bucket_minutes,
                seed=seed + index,
            )
        )
    return manifests
