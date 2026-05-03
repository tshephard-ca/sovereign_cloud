from __future__ import annotations

from cabinet_burst_envelope.cli import _prepare_estimate

from .conftest import (
    NOW,
    base_profile,
    generated_power_rows,
    generated_temperature_rows,
    write_power_rows,
    write_profile,
    write_temperature_rows,
)


def _estimate(tmp_path, profile_data=None, power_rows=None, temp_rows=None):
    profile = write_profile(tmp_path, profile_data or base_profile())
    power = write_power_rows(tmp_path, power_rows or generated_power_rows())
    temp = write_temperature_rows(tmp_path, temp_rows or generated_temperature_rows())
    return _prepare_estimate(power, temp, profile, None, 7, 5, False, NOW)


def test_produces_ready_for_review_for_good_data_and_margins(tmp_path):
    profile = base_profile()
    profile["thermal"]["max_thermal_extrapolation_kw"] = 100.0
    _loaded, _alignment, envelope, _summary = _estimate(tmp_path, profile)
    assert envelope.envelope_status == "READY_FOR_REVIEW"
    assert envelope.confidence == "HIGH"
    assert envelope.recommended_sustained_kw == 21.6


def test_produces_review_required_for_incomplete_but_usable_data(tmp_path):
    profile = base_profile()
    profile["thermal"]["max_thermal_extrapolation_kw"] = 100.0
    temps = generated_temperature_rows(include_top=False)
    _loaded, _alignment, envelope, _summary = _estimate(tmp_path, profile, temp_rows=temps)
    assert envelope.envelope_status == "REVIEW_REQUIRED"
    assert "MISSING_TOP_INLET_SENSOR" in envelope.missing_data


def test_produces_do_not_expand_when_current_load_exceeds_guardrail(tmp_path):
    profile = base_profile()
    profile["electrical"]["usable_sustained_kw"] = 18.0
    profile["electrical"]["usable_burst_kw"] = 20.0
    _loaded, _alignment, envelope, _summary = _estimate(tmp_path, profile, power_rows=generated_power_rows(base_kw=19, variation_kw=2))
    assert envelope.envelope_status == "DO_NOT_EXPAND"
    assert "CURRENT_SUSTAINED_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL" in envelope.blockers


def test_produces_insufficient_data_when_aligned_coverage_too_low(tmp_path):
    _loaded, _alignment, envelope, _summary = _estimate(
        tmp_path,
        power_rows=generated_power_rows(every=20),
        temp_rows=generated_temperature_rows(every=20),
    )
    assert envelope.envelope_status == "INSUFFICIENT_DATA"
    assert "ALIGNED_COVERAGE_TOO_LOW" in envelope.blockers
    assert envelope.recommended_sustained_kw is None
    assert envelope.recommended_short_burst_kw is None


def test_all_zero_power_blocks_envelope_by_default(tmp_path):
    rows = generated_power_rows(base_kw=0, variation_kw=0)
    for row in rows:
        row["reading_kw"] = 0
    _loaded, _alignment, envelope, _summary = _estimate(tmp_path, power_rows=rows)
    assert envelope.envelope_status == "INSUFFICIENT_DATA"
    assert "ALL_ZERO_POWER_READINGS" in envelope.blockers
    assert envelope.recommended_sustained_kw is None


def test_envelope_json_shape_has_required_fields(tmp_path):
    _loaded, _alignment, envelope, _summary = _estimate(tmp_path)
    payload = envelope.model_dump(mode="json")
    assert payload["cabinet_id"] == "cab-test"
    assert "observed_power" in payload
    assert "observed_temperature" in payload
    assert "sales_ops_guardrail" in payload
    assert "REVIEW_ONLY_OUTPUT" in payload["reason_codes"]
    assert "REVIEW_ONLY_OUTPUT" not in payload["warnings"]
