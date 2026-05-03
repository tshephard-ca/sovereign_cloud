from __future__ import annotations

import pytest

from cabinet_burst_envelope.parse_power import parse_power_csv

from .conftest import NOW, generated_power_rows, write_power_rows


def test_parses_valid_pdu_power_csv(tmp_path):
    path = write_power_rows(tmp_path, generated_power_rows(count=2))
    result = parse_power_csv(path)
    assert len(result.rows) == 4
    assert result.rows[0].reading_kw > 0
    assert "POWER_DATA_PRESENT" in result.reason_codes


def test_strict_fails_when_power_csv_missing(tmp_path):
    with pytest.raises(ValueError, match="power CSV is required"):
        parse_power_csv(tmp_path / "missing.csv", strict=True)


def test_strict_fails_when_multiple_cabinet_ids_are_present(tmp_path):
    rows = generated_power_rows(cabinet_id="cab-one", count=1) + generated_power_rows(cabinet_id="cab-two", count=1)
    path = write_power_rows(tmp_path, rows)
    with pytest.raises(ValueError, match="multiple cabinet IDs"):
        parse_power_csv(path, strict=True)


def test_unknown_scope_and_quality_warnings(tmp_path):
    rows = [
        {"timestamp": NOW, "cabinet_id": "cab-test", "reading_scope": "unknown", "reading_kw": 10, "reading_quality": "estimated"},
        {"timestamp": NOW, "cabinet_id": "cab-test", "reading_scope": "unknown", "reading_kw": 11, "reading_quality": "stale"},
    ]
    path = write_power_rows(tmp_path, rows)
    result = parse_power_csv(path)
    assert "READING_SCOPE_UNKNOWN" in result.warnings
    assert "ESTIMATED_POWER_READINGS_PRESENT" in result.warnings
    assert "STALE_POWER_READINGS_PRESENT" in result.warnings


def test_ignores_missing_quality_rows(tmp_path):
    rows = [
        {"timestamp": NOW, "cabinet_id": "cab-test", "reading_scope": "total_cabinet", "reading_kw": 10, "reading_quality": "missing"},
        {"timestamp": NOW, "cabinet_id": "cab-test", "reading_scope": "total_cabinet", "reading_kw": 12, "reading_quality": "good"},
    ]
    result = parse_power_csv(write_power_rows(tmp_path, rows))
    assert len(result.rows) == 1
    assert result.rows[0].reading_kw == 12


def test_naive_timestamp_warns_timezone_unknown(tmp_path):
    rows = [{"timestamp": "2025-12-31T23:55:00", "cabinet_id": "cab-test", "reading_scope": "total_cabinet", "reading_kw": 10}]
    result = parse_power_csv(write_power_rows(tmp_path, rows))
    assert "TIMESTAMP_TIMEZONE_UNKNOWN" in result.warnings
