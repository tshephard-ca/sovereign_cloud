from __future__ import annotations

import pytest

from cabinet_burst_envelope.parse_temperature import parse_temperature_csv

from .conftest import NOW, generated_temperature_rows, write_temperature_rows


def test_parses_valid_inlet_temperature_csv(tmp_path):
    path = write_temperature_rows(tmp_path, generated_temperature_rows(count=2))
    result = parse_temperature_csv(path)
    assert len(result.rows) == 6
    assert result.rows[0].sensor_role == "inlet"
    assert "TEMPERATURE_DATA_PRESENT" in result.reason_codes


def test_strict_fails_when_temperature_csv_missing(tmp_path):
    with pytest.raises(ValueError, match="temperature CSV is required"):
        parse_temperature_csv(tmp_path / "missing.csv", strict=True)


def test_temperature_ignores_missing_and_warns_stale_estimated(tmp_path):
    rows = [
        {"timestamp": NOW, "cabinet_id": "cab-test", "sensor_id": "sensor-top", "position": "front_top", "height": "top", "sensor_role": "inlet", "inlet_temp_c": 22, "reading_quality": "missing"},
        {"timestamp": NOW, "cabinet_id": "cab-test", "sensor_id": "sensor-mid", "position": "front_middle", "height": "middle", "sensor_role": "inlet", "inlet_temp_c": 23, "reading_quality": "estimated"},
        {"timestamp": NOW, "cabinet_id": "cab-test", "sensor_id": "sensor-bottom", "position": "front_bottom", "height": "bottom", "sensor_role": "inlet", "inlet_temp_c": 21, "reading_quality": "stale"},
    ]
    result = parse_temperature_csv(write_temperature_rows(tmp_path, rows))
    assert len(result.rows) == 2
    assert "ESTIMATED_TEMPERATURE_READINGS_PRESENT" in result.warnings
    assert "STALE_TEMPERATURE_READINGS_PRESENT" in result.warnings


def test_temperature_strict_rejects_multiple_cabinets(tmp_path):
    rows = generated_temperature_rows(cabinet_id="cab-one", count=1) + generated_temperature_rows(cabinet_id="cab-two", count=1)
    with pytest.raises(ValueError, match="multiple cabinet IDs"):
        parse_temperature_csv(write_temperature_rows(tmp_path, rows), strict=True)
