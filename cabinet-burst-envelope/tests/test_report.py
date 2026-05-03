from __future__ import annotations

import csv
import json

from cabinet_burst_envelope.cli import _prepare_estimate
from cabinet_burst_envelope.report import TIMESERIES_COLUMNS, write_aligned_timeseries_csv, write_guardrail_markdown, write_json

from .conftest import NOW, generated_power_rows, generated_temperature_rows, write_power_rows, write_profile, write_temperature_rows


def test_writes_aligned_timeseries_with_exact_column_order(tmp_path):
    profile = write_profile(tmp_path)
    power = write_power_rows(tmp_path, generated_power_rows(count=2))
    temp = write_temperature_rows(tmp_path, generated_temperature_rows(count=2))
    _loaded, alignment, _envelope, _summary = _prepare_estimate(power, temp, profile, None, 7, 5, False, NOW)
    output = tmp_path / "aligned.csv"
    write_aligned_timeseries_csv(output, alignment)
    with output.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        assert next(reader) == TIMESERIES_COLUMNS


def test_writes_summary_json_with_expected_fields(tmp_path):
    profile = write_profile(tmp_path)
    power = write_power_rows(tmp_path, generated_power_rows())
    temp = write_temperature_rows(tmp_path, generated_temperature_rows())
    _loaded, _alignment, _envelope, summary = _prepare_estimate(power, temp, profile, None, 7, 5, False, NOW)
    output = tmp_path / "summary.json"
    write_json(output, summary)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert set(payload) >= {"cabinet_id", "input", "recommendation", "risk", "reason_code_counts"}


def test_markdown_guardrail_contains_review_only_language(tmp_path):
    profile = write_profile(tmp_path)
    power = write_power_rows(tmp_path, generated_power_rows())
    temp = write_temperature_rows(tmp_path, generated_temperature_rows())
    _loaded, _alignment, envelope, _summary = _prepare_estimate(power, temp, profile, None, 7, 5, False, NOW)
    output = tmp_path / "guardrail.md"
    write_guardrail_markdown(output, envelope)
    text = output.read_text(encoding="utf-8")
    assert "review-only" in text.lower()
    assert "Reason Codes" in text
    assert "Data Honesty Caveats" in text


def test_json_output_ordering_is_deterministic(tmp_path):
    profile = write_profile(tmp_path)
    power = write_power_rows(tmp_path, generated_power_rows())
    temp = write_temperature_rows(tmp_path, generated_temperature_rows())
    _loaded, _alignment, envelope, _summary = _prepare_estimate(power, temp, profile, None, 7, 5, False, NOW)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_json(first, envelope)
    write_json(second, envelope)
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
