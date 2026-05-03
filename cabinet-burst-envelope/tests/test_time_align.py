from __future__ import annotations

from cabinet_burst_envelope.parse_power import parse_power_csv
from cabinet_burst_envelope.parse_temperature import parse_temperature_csv
from cabinet_burst_envelope.time_align import align_timeseries

from .conftest import NOW, generated_power_rows, generated_temperature_rows, write_power_rows, write_temperature_rows


def _align(tmp_path, power_rows, temp_rows, config):
    power = parse_power_csv(write_power_rows(tmp_path, power_rows)).rows
    temp = parse_temperature_csv(write_temperature_rows(tmp_path, temp_rows)).rows
    return align_timeseries(power, temp, "cab-test", config, now=NOW)


def test_aligns_power_and_temperature_into_5_minute_buckets(tmp_path, default_config):
    alignment = _align(tmp_path, generated_power_rows(count=12), generated_temperature_rows(count=12), default_config)
    assert len(alignment.buckets) == 2016
    assert alignment.buckets[0].cabinet_power_kw is not None
    assert alignment.buckets[0].max_inlet_temp_c is not None
    assert alignment.buckets[0].aligned_bucket_quality == "good"


def test_feed_total_readings_are_summed(tmp_path, default_config):
    alignment = _align(tmp_path, generated_power_rows(count=1, scope="feed_total"), generated_temperature_rows(count=1), default_config)
    first = alignment.buckets[0]
    assert first.feed_power_kw["A"] + first.feed_power_kw["B"] == first.cabinet_power_kw


def test_total_cabinet_readings_are_not_double_counted(tmp_path, default_config):
    alignment = _align(tmp_path, generated_power_rows(count=1, scope="total_cabinet"), generated_temperature_rows(count=1), default_config)
    assert alignment.buckets[0].cabinet_power_kw == 16.0
    assert alignment.buckets[0].feed_power_kw == {}


def test_coverage_percentages_and_long_gaps(tmp_path, default_config):
    alignment = _align(
        tmp_path,
        generated_power_rows(count=2016, every=2),
        generated_temperature_rows(count=2016, every=3),
        default_config,
    )
    assert 49 < alignment.coverage.power_coverage_pct < 51
    assert 33 < alignment.coverage.temperature_coverage_pct < 34
    assert 16 < alignment.coverage.aligned_coverage_pct < 17
    assert "POWER_COVERAGE_LOW" in alignment.warnings
    assert "TEMPERATURE_COVERAGE_LOW" in alignment.warnings


def test_detects_long_power_and_temperature_gaps(tmp_path, default_config):
    power_rows = generated_power_rows(count=2016)
    temp_rows = generated_temperature_rows(count=2016)
    power_rows = [row for index, row in enumerate(power_rows) if not 100 <= index // 2 < 120]
    temp_rows = [row for index, row in enumerate(temp_rows) if not 200 <= index // 3 < 220]
    alignment = _align(tmp_path, power_rows, temp_rows, default_config)
    assert alignment.coverage.longest_power_gap_minutes >= 100
    assert alignment.coverage.longest_temperature_gap_minutes >= 100
    assert "LONG_POWER_GAP" in alignment.warnings
    assert "LONG_TEMPERATURE_GAP" in alignment.warnings


def test_no_valid_inlet_sensor_is_flagged(tmp_path, default_config):
    temp_rows = [
        {"timestamp": "2025-12-25T00:00:00Z", "cabinet_id": "cab-test", "sensor_id": "sensor-ambient", "position": "ambient", "height": "unknown", "sensor_role": "ambient", "inlet_temp_c": 22}
    ]
    alignment = _align(tmp_path, generated_power_rows(count=1), temp_rows, default_config)
    assert "NO_VALID_INLET_SENSOR" in alignment.missing_data
