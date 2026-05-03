from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cabinet_burst_envelope.models import TimeBucket
from cabinet_burst_envelope.statistics import compute_power_stats, compute_temperature_stats, percentile


def _buckets(values: list[float], temps: list[float] | None = None) -> list[TimeBucket]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    buckets = []
    for index, value in enumerate(values):
        temp = temps[index] if temps else None
        buckets.append(
            TimeBucket(
                timestamp=start + timedelta(minutes=5 * index),
                cabinet_id="cab-test",
                cabinet_power_kw=value,
                feed_power_kw={"A": value * 0.5, "B": value * 0.5},
                max_inlet_temp_c=temp,
                top_inlet_temp_c=temp + 1 if temp is not None else None,
                middle_inlet_temp_c=temp if temp is not None else None,
                bottom_inlet_temp_c=temp - 1 if temp is not None else None,
                power_bucket_quality="good",
                temperature_bucket_quality="good" if temp is not None else "missing",
                aligned_bucket_quality="good" if temp is not None else "partial",
            )
        )
    return buckets


def test_percentile_is_deterministic():
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([1, 2, 3, 4], 95) == 3.8499999999999996


def test_computes_observed_power_metrics_and_rolling_windows():
    stats = compute_power_stats(_buckets(list(range(1, 25))), 5, sustained_window_minutes=60, burst_window_minutes=5)
    assert stats.observed_power_p50_kw == 12.5
    assert stats.observed_power_p95_kw == 22.85
    assert stats.observed_power_max_kw == 24
    assert stats.observed_sustained_p95_kw is not None
    assert stats.observed_short_burst_p99_kw == 23.77
    assert stats.observed_power_ramp_max_kw_per_min == 0.2


def test_computes_temperature_metrics_and_hotspot():
    stats = compute_temperature_stats(_buckets([10, 11, 12], [20, 21, 22]), 5, True, hotspot_delta_top_bottom_c=1.5)
    assert stats.observed_inlet_p50_c == 21
    assert stats.observed_inlet_max_c == 22
    assert stats.hotspot_delta_top_bottom_c == 2
    assert "HOTSPOT_TOP_INLET" in stats.reason_codes
    assert "TOP_MIDDLE_BOTTOM_SENSORS_PRESENT" in stats.reason_codes


def test_detects_missing_top_middle_bottom_sensors():
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    buckets = [
        TimeBucket(timestamp=start, cabinet_id="cab-test", max_inlet_temp_c=20, bottom_inlet_temp_c=20),
    ]
    stats = compute_temperature_stats(buckets, 5, True, hotspot_delta_top_bottom_c=4)
    assert "MISSING_TOP_INLET_SENSOR" in stats.missing_data
    assert "MISSING_MIDDLE_INLET_SENSOR" in stats.missing_data
    assert "MISSING_BOTTOM_INLET_SENSOR" not in stats.missing_data
