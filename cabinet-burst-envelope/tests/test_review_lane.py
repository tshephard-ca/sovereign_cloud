from __future__ import annotations

from cabinet_burst_envelope.cli import _prepare_estimate
from cabinet_burst_envelope.decision import classify_review_lane

from .conftest import NOW, base_profile, generated_power_rows, generated_temperature_rows, write_power_rows, write_profile, write_temperature_rows


def _envelope(tmp_path, profile=None, power_rows=None, temperature_rows=None):
    profile_path = write_profile(tmp_path, profile)
    power_path = write_power_rows(tmp_path, power_rows or generated_power_rows())
    temp_path = write_temperature_rows(tmp_path, temperature_rows or generated_temperature_rows())
    _loaded, _alignment, envelope, _summary = _prepare_estimate(power_path, temp_path, profile_path, None, 7, 5, False, NOW)
    return envelope


def test_ready_envelope_maps_to_facility_review_lane(tmp_path):
    envelope = _envelope(tmp_path)
    decision = classify_review_lane(envelope)
    assert decision.lane == "READY_FOR_FACILITY_REVIEW"
    assert decision.next_actions[0].action_id == "start_facility_review_packet"


def test_missing_sensor_maps_to_collect_evidence_lane(tmp_path):
    envelope = _envelope(tmp_path, temperature_rows=generated_temperature_rows(include_top=False))
    decision = classify_review_lane(envelope)
    assert decision.lane == "COLLECT_EVIDENCE"
    assert "sensor_remediation" in decision.remediation_categories
    assert any(action.action_id == "restore_inlet_sensor_coverage" for action in decision.next_actions)


def test_electrical_blocker_maps_to_stop_expansion_lane(tmp_path):
    profile = base_profile()
    profile["electrical"]["usable_sustained_kw"] = 16.0
    profile["electrical"]["usable_burst_kw"] = 17.0
    profile["electrical"]["trip_risk_kw"] = 18.0
    envelope = _envelope(tmp_path, profile=profile, power_rows=generated_power_rows(base_kw=20.0, variation_kw=2.0))
    decision = classify_review_lane(envelope)
    assert decision.lane == "STOP_EXPANSION_DISCUSSION"
    assert decision.primary_constraint == "electrical"
    assert any(action.action_id == "review_electrical_guardrail" for action in decision.next_actions)


def test_hotspot_warning_maps_to_remediation_lane(tmp_path):
    envelope = _envelope(tmp_path, temperature_rows=generated_temperature_rows(top_delta=6.0))
    decision = classify_review_lane(envelope)
    assert decision.lane in {"NEEDS_REMEDIATION", "STOP_EXPANSION_DISCUSSION"}
    assert "thermal_limited" in decision.remediation_categories
