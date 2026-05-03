from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cabinet_burst_envelope.models import CabinetProfile, TimeBucket
from cabinet_burst_envelope.statistics import compute_power_stats, compute_temperature_stats
from cabinet_burst_envelope.thermal import calculate_thermal_envelope, fit_thermal_model

from .conftest import base_profile


def _thermal_buckets(slope: float = 0.12, power_variation: float = 6.0, temp_variation: bool = True):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    buckets = []
    for i in range(36):
        power = 10 + power_variation * i / 35
        temp = 20 + slope * power if temp_variation else 22.0
        buckets.append(
            TimeBucket(
                timestamp=start + timedelta(minutes=5 * i),
                cabinet_id="cab-test",
                cabinet_power_kw=power,
                max_inlet_temp_c=temp,
                top_inlet_temp_c=temp,
                middle_inlet_temp_c=temp - 0.5,
                bottom_inlet_temp_c=temp - 1.0,
            )
        )
    return buckets


def test_fits_usable_thermal_model(default_config):
    result = fit_thermal_model(_thermal_buckets(), default_config, inlet_warning_c=30, inlet_critical_c=34)
    assert result.thermal_model_status == "USABLE"
    assert result.slope_c_per_kw is not None and result.slope_c_per_kw > 0
    assert result.r_squared == 1.0
    assert "THERMAL_MODEL_USABLE" in result.reason_codes


def test_rejects_thermal_model_when_power_variation_too_low(default_config):
    result = fit_thermal_model(_thermal_buckets(power_variation=0.1), default_config, 30, 34)
    assert result.thermal_model_status == "UNUSABLE"
    assert "POWER_VARIATION_TOO_LOW_FOR_THERMAL_MODEL" in result.reason_codes


def test_rejects_thermal_model_when_temperature_variation_too_low(default_config):
    result = fit_thermal_model(_thermal_buckets(temp_variation=False), default_config, 30, 34)
    assert result.thermal_model_status == "UNUSABLE"
    assert "TEMP_VARIATION_TOO_LOW_FOR_THERMAL_MODEL" in result.reason_codes


def test_rejects_thermal_model_when_slope_non_positive(default_config):
    result = fit_thermal_model(_thermal_buckets(slope=-0.12), default_config, 30, 34)
    assert result.thermal_model_status == "UNUSABLE"
    assert "THERMAL_SLOPE_NOT_POSITIVE" in result.reason_codes


def test_caps_thermal_extrapolation(default_config):
    profile = CabinetProfile.model_validate(base_profile())
    profile.thermal.max_thermal_extrapolation_kw = 1.0
    buckets = _thermal_buckets(slope=0.12)
    power_stats = compute_power_stats(buckets, 5, 60, 5)
    temp_stats = compute_temperature_stats(buckets, 5, True, 4)
    model = fit_thermal_model(buckets, default_config, 30, 34)
    thermal = calculate_thermal_envelope(temp_stats, power_stats, model, profile, default_config)
    assert "THERMAL_EXTRAPOLATION_CAPPED" in thermal.thermal_reason_codes
    assert thermal.thermal_guardrail_sustained_kw == power_stats.observed_power_max_kw + 1.0


def test_reports_best_thermal_lag(default_config):
    buckets = _thermal_buckets(slope=0.12)
    shifted = []
    for index, bucket in enumerate(buckets):
        payload = bucket.model_copy()
        payload.max_inlet_temp_c = buckets[max(0, index - 2)].max_inlet_temp_c
        shifted.append(payload)
    result = fit_thermal_model(shifted, default_config, 30, 34)
    assert result.best_lag_minutes >= 0
    assert result.best_lag_r_squared is not None
