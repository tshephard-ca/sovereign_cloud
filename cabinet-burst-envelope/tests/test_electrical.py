from __future__ import annotations

from cabinet_burst_envelope.electrical import calculate_electrical_envelope
from cabinet_burst_envelope.models import CabinetProfile, PowerStats

from .conftest import base_profile


def test_computes_electrical_sustained_and_burst_guardrails(default_config):
    profile = CabinetProfile.model_validate(base_profile())
    stats = PowerStats(observed_sustained_p95_kw=18, observed_short_burst_p99_kw=20, feed_imbalance_pct=8)
    env = calculate_electrical_envelope(stats, profile, default_config)
    assert env.electrical_guardrail_sustained_kw == 21.6
    assert env.electrical_guardrail_burst_kw == 25.6
    assert env.electrical_risk == "LOW"


def test_warns_when_burst_limit_and_trip_threshold_not_supplied(default_config):
    data = base_profile()
    data["electrical"].pop("usable_burst_kw")
    data["electrical"].pop("trip_risk_kw")
    env = calculate_electrical_envelope(PowerStats(observed_sustained_p95_kw=10), CabinetProfile.model_validate(data), default_config)
    assert "BURST_LIMIT_NOT_SUPPLIED" in env.warnings
    assert "TRIP_THRESHOLD_NOT_SUPPLIED" in env.warnings
    assert env.electrical_burst_limit_kw == env.electrical_sustained_limit_kw


def test_detects_medium_and_high_trip_risk(default_config):
    profile = CabinetProfile.model_validate(base_profile())
    medium = calculate_electrical_envelope(PowerStats(observed_short_burst_p99_kw=28.5), profile, default_config)
    high = calculate_electrical_envelope(PowerStats(observed_short_burst_p99_kw=29.5), profile, default_config)
    assert "MEDIUM_TRIP_RISK" in medium.warnings
    assert "HIGH_TRIP_RISK" in high.blockers


def test_detects_feed_imbalance_warning_and_critical(default_config):
    profile = CabinetProfile.model_validate(base_profile())
    warning = calculate_electrical_envelope(PowerStats(observed_sustained_p95_kw=10, feed_imbalance_pct=25), profile, default_config)
    critical = calculate_electrical_envelope(PowerStats(observed_sustained_p95_kw=10, feed_imbalance_pct=40), profile, default_config)
    assert "FEED_IMBALANCE_WARNING" in warning.warnings
    assert "FEED_IMBALANCE_CRITICAL" in critical.blockers


def test_current_load_exceeding_guardrail_blocks_expansion(default_config):
    profile = CabinetProfile.model_validate(base_profile())
    env = calculate_electrical_envelope(PowerStats(observed_sustained_p95_kw=23, observed_short_burst_p99_kw=27), profile, default_config)
    assert "CURRENT_SUSTAINED_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL" in env.blockers
    assert "CURRENT_BURST_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL" in env.blockers
