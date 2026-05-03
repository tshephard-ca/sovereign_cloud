from __future__ import annotations

from collections import Counter
from datetime import datetime

from .guardrail import generate_sales_ops_guardrail, recommended_questions
from .models import (
    AlignmentResult,
    CabinetEnvelope,
    CabinetProfile,
    ElectricalEnvelope,
    PowerStats,
    Summary,
    TemperatureStats,
    ThermalEnvelope,
)
from .normalize import add_unique, floor_one_decimal, isoformat_z, round_float


INSUFFICIENT_BLOCKERS = {
    "POWER_DATA_MISSING",
    "TEMPERATURE_DATA_MISSING",
    "CABINET_PROFILE_MISSING",
    "NO_VALID_INLET_SENSOR",
    "ELECTRICAL_LIMIT_MISSING",
    "MULTIPLE_CABINETS_IN_INPUT",
    "ALIGNED_COVERAGE_TOO_LOW",
    "PROFILE_INVALID",
    "ALL_ZERO_POWER_READINGS",
}

DO_NOT_EXPAND_BLOCKERS = {
    "CURRENT_SUSTAINED_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL",
    "CURRENT_BURST_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL",
    "INLET_TEMP_CRITICAL_OBSERVED",
    "HIGH_TRIP_RISK",
    "FEED_IMBALANCE_CRITICAL",
    "SINGLE_FEED_SURVIVAL_RISK",
}


def _merge_lists(*lists: list[str]) -> list[str]:
    out: list[str] = []
    for values in lists:
        for value in values:
            add_unique(out, value)
    return out


def _add_envelope_reason(status: str, reason_codes: list[str]) -> None:
    if status == "READY_FOR_REVIEW":
        add_unique(reason_codes, "ENVELOPE_READY_FOR_REVIEW")
    elif status == "REVIEW_REQUIRED":
        add_unique(reason_codes, "ENVELOPE_REVIEW_REQUIRED")
    elif status == "DO_NOT_EXPAND":
        add_unique(reason_codes, "ENVELOPE_DO_NOT_EXPAND")
    elif status == "INSUFFICIENT_DATA":
        add_unique(reason_codes, "ENVELOPE_INSUFFICIENT_DATA")


def _determine_limiting_factor(electrical_candidate: float | None, thermal_candidate: float | None, data_quality_limited: bool) -> str:
    if data_quality_limited:
        return "DATA_QUALITY"
    if electrical_candidate is None and thermal_candidate is None:
        return "UNKNOWN"
    if electrical_candidate is not None and thermal_candidate is not None:
        if abs(electrical_candidate - thermal_candidate) < 0.05:
            return "BOTH"
        return "ELECTRICAL" if electrical_candidate < thermal_candidate else "THERMAL"
    if electrical_candidate is not None:
        return "ELECTRICAL"
    return "THERMAL"


def _limit_reason(limiting_factor: str, reason_codes: list[str]) -> None:
    mapping = {
        "ELECTRICAL": "LIMITING_FACTOR_ELECTRICAL",
        "THERMAL": "LIMITING_FACTOR_THERMAL",
        "BOTH": "LIMITING_FACTOR_BOTH",
        "DATA_QUALITY": "LIMITING_FACTOR_DATA_QUALITY",
    }
    code = mapping.get(limiting_factor)
    if code:
        add_unique(reason_codes, code)


def _confidence(
    alignment: AlignmentResult,
    profile: CabinetProfile | None,
    temp_stats: TemperatureStats,
    thermal_env: ThermalEnvelope,
    electrical_env: ElectricalEnvelope,
    warnings: list[str],
    recommended_sustained_kw: float | None,
    recommended_burst_kw: float | None,
    config: dict,
) -> str:
    if recommended_sustained_kw is None or recommended_burst_kw is None:
        return "LOW"
    if any(code in warnings for code in ("TIMESTAMP_TIMEZONE_UNKNOWN", "MISSING_TOP_INLET_SENSOR")):
        return "LOW"
    if alignment.coverage.aligned_coverage_pct < float(config["minimum_coverage_pct"]):
        return "LOW" if alignment.coverage.aligned_coverage_pct < 75 else "MEDIUM"
    if profile is None:
        return "LOW"
    has_required_profile = (
        profile.electrical.usable_sustained_kw is not None
        and profile.electrical.usable_burst_kw is not None
        and profile.electrical.trip_risk_kw is not None
        and profile.thermal.inlet_warning_c is not None
        and profile.thermal.inlet_critical_c is not None
    )
    has_sensors = "TOP_MIDDLE_BOTTOM_SENSORS_PRESENT" in temp_stats.reason_codes
    thermal_ok = thermal_env.thermal_model_status == "USABLE" or (
        not profile.thermal.thermal_model_required_for_burst
        and thermal_env.thermal_headroom_c is not None
        and thermal_env.thermal_headroom_c > float(config["medium_thermal_risk_margin_c"])
    )
    major_warnings = [
        code
        for code in warnings
        if code
        not in {
            "REVIEW_ONLY_OUTPUT",
            "HUMAN_REVIEW_REQUIRED",
        }
    ]
    if (
        has_required_profile
        and has_sensors
        and thermal_ok
        and not major_warnings
        and electrical_env.electrical_risk == "LOW"
        and thermal_env.thermal_risk == "LOW"
    ):
        return "HIGH"
    if has_required_profile and recommended_sustained_kw is not None:
        return "MEDIUM"
    return "LOW"


def _evidence_quality(
    alignment: AlignmentResult,
    temp_stats: TemperatureStats,
    warnings: list[str],
    missing_data: list[str],
    blockers: list[str],
    thermal_env: ThermalEnvelope,
    electrical_env: ElectricalEnvelope,
) -> dict[str, object]:
    score = 100
    score -= max(0, int(100 - alignment.coverage.power_coverage_pct)) // 2
    score -= max(0, int(100 - alignment.coverage.temperature_coverage_pct)) // 2
    score -= max(0, int(100 - alignment.coverage.aligned_coverage_pct)) // 2
    score -= min(30, len(missing_data) * 8)
    score -= min(25, len([warning for warning in warnings if warning != "REVIEW_ONLY_OUTPUT"]) * 4)
    score -= min(40, len(blockers) * 12)
    if thermal_env.thermal_model_status == "UNUSABLE":
        score -= 10
    if electrical_env.trip_risk_threshold_kw is None:
        score -= 5
    if "TOP_MIDDLE_BOTTOM_SENSORS_PRESENT" not in temp_stats.reason_codes:
        score -= 10
    score = max(0, min(100, score))
    if score >= 85:
        band = "HIGH"
    elif score >= 65:
        band = "MEDIUM"
    else:
        band = "LOW"
    return {
        "score": score,
        "band": band,
        "coverage": alignment.coverage.model_dump(mode="json"),
        "thermal_model_status": thermal_env.thermal_model_status,
        "top_middle_bottom_sensors_present": "TOP_MIDDLE_BOTTOM_SENSORS_PRESENT" in temp_stats.reason_codes,
        "warning_count": len(warnings),
        "blocker_count": len(blockers),
        "missing_data_count": len(missing_data),
    }


def calculate_cabinet_envelope(
    profile: CabinetProfile | None,
    alignment: AlignmentResult,
    power_stats: PowerStats,
    temp_stats: TemperatureStats,
    electrical_env: ElectricalEnvelope,
    thermal_env: ThermalEnvelope,
    generated_at: datetime,
    config: dict,
    input_reason_codes: list[str] | None = None,
    input_warnings: list[str] | None = None,
    input_missing_data: list[str] | None = None,
) -> CabinetEnvelope:
    reason_codes = _merge_lists(
        input_reason_codes or [],
        alignment.reason_codes,
        temp_stats.reason_codes,
        electrical_env.electrical_reason_codes,
        thermal_env.thermal_reason_codes,
    )
    blockers = _merge_lists(electrical_env.blockers, thermal_env.blockers)
    warnings = _merge_lists(input_warnings or [], alignment.warnings, electrical_env.warnings, thermal_env.warnings)
    missing_data = _merge_lists(input_missing_data or [], alignment.missing_data, temp_stats.missing_data)
    assumptions: list[str] = [
        "Seven days of telemetry may not include worst-case weather, cooling failures, maintenance modes, or workload peaks.",
        "PDU power telemetry is not a full electrical study.",
        "Inlet-temperature telemetry is not CFD.",
        "A simple thermal slope is not proof of cooling capacity.",
        "Trip-risk thresholds come from the user profile, not from this tool.",
    ]

    if profile is None:
        add_unique(reason_codes, "CABINET_PROFILE_MISSING")
        add_unique(blockers, "CABINET_PROFILE_MISSING")
        add_unique(missing_data, "CABINET_PROFILE_MISSING")
    if "PROFILE_INVALID" in reason_codes or "PROFILE_INVALID" in missing_data:
        add_unique(blockers, "PROFILE_INVALID")
        add_unique(missing_data, "PROFILE_INVALID")
    if "NO_VALID_INLET_SENSOR" in reason_codes or "NO_VALID_INLET_SENSOR" in missing_data:
        add_unique(blockers, "NO_VALID_INLET_SENSOR")
        add_unique(missing_data, "NO_VALID_INLET_SENSOR")
    if alignment.coverage.power_buckets == 0:
        add_unique(reason_codes, "POWER_DATA_MISSING")
        add_unique(blockers, "POWER_DATA_MISSING")
        add_unique(missing_data, "POWER_DATA_MISSING")
    if alignment.coverage.temperature_buckets == 0:
        add_unique(reason_codes, "TEMPERATURE_DATA_MISSING")
        add_unique(blockers, "TEMPERATURE_DATA_MISSING")
        add_unique(missing_data, "TEMPERATURE_DATA_MISSING")
    if "ALL_ZERO_POWER_READINGS" in reason_codes and not bool(config.get("allow_all_zero_power", False)):
        add_unique(blockers, "ALL_ZERO_POWER_READINGS")

    usable_aligned_minutes = alignment.coverage.aligned_buckets * alignment.bucket_minutes
    if alignment.coverage.aligned_coverage_pct < 50 or usable_aligned_minutes < 24 * 60:
        add_unique(blockers, "ALIGNED_COVERAGE_TOO_LOW")
        add_unique(reason_codes, "ALIGNED_COVERAGE_LOW")

    thermal_do_not_expand = (
        "INLET_TEMP_WARNING_OBSERVED" in reason_codes
        or "CURRENT_LOAD_NEAR_OR_ABOVE_THERMAL_LIMIT" in reason_codes
    )
    if profile and profile.sales_policy.require_facility_review_above_kw is not None:
        observed = power_stats.observed_sustained_p95_kw or power_stats.observed_power_p95_kw
        if observed is not None and observed > profile.sales_policy.require_facility_review_above_kw:
            add_unique(reason_codes, "HUMAN_REVIEW_REQUIRED")

    electrical_candidate_sustained = electrical_env.electrical_guardrail_sustained_kw
    thermal_candidate_sustained = thermal_env.thermal_guardrail_sustained_kw
    sustained_candidates = [value for value in [electrical_candidate_sustained, thermal_candidate_sustained] if value is not None]
    recommended_sustained = min(sustained_candidates) if sustained_candidates else None

    electrical_candidate_burst = electrical_env.electrical_guardrail_burst_kw
    thermal_candidate_burst = thermal_env.thermal_guardrail_burst_kw
    burst_candidates = [value for value in [electrical_candidate_burst, thermal_candidate_burst] if value is not None]
    recommended_burst = min(burst_candidates) if burst_candidates else None
    if recommended_burst is not None and electrical_env.trip_risk_threshold_kw is not None:
        recommended_burst = min(recommended_burst, electrical_env.trip_risk_threshold_kw)
    if recommended_burst is not None and recommended_sustained is not None and "BURST_LIMIT_NOT_SUPPLIED" in reason_codes:
        recommended_burst = min(recommended_burst, recommended_sustained)

    recommended_sustained = floor_one_decimal(recommended_sustained)
    recommended_burst = floor_one_decimal(recommended_burst)
    if recommended_sustained == 0.0 or recommended_burst == 0.0:
        add_unique(reason_codes, "ENVELOPE_DO_NOT_EXPAND")
        add_unique(blockers, "CURRENT_SUSTAINED_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL")

    data_quality_limited = bool(set(blockers) & INSUFFICIENT_BLOCKERS)
    limiting_factor = _determine_limiting_factor(electrical_candidate_sustained, thermal_candidate_sustained, data_quality_limited)
    _limit_reason(limiting_factor, reason_codes)
    add_unique(reason_codes, "REVIEW_ONLY_OUTPUT")

    confidence = _confidence(
        alignment,
        profile,
        temp_stats,
        thermal_env,
        electrical_env,
        warnings,
        recommended_sustained,
        recommended_burst,
        config,
    )
    if "PROFILE_INVALID" in missing_data:
        confidence = "LOW"
    if confidence == "LOW":
        add_unique(reason_codes, "LOW_CONFIDENCE_DISCUSSION_GUARDRAIL")

    substantive_warnings = list(warnings)
    if set(blockers) & INSUFFICIENT_BLOCKERS:
        status = "INSUFFICIENT_DATA"
    elif set(blockers) & DO_NOT_EXPAND_BLOCKERS or thermal_do_not_expand or "ENVELOPE_DO_NOT_EXPAND" in reason_codes:
        status = "DO_NOT_EXPAND"
    elif recommended_sustained is None or recommended_burst is None:
        status = "INSUFFICIENT_DATA"
    elif substantive_warnings or confidence in {"LOW", "MEDIUM"}:
        status = "REVIEW_REQUIRED"
    else:
        status = "READY_FOR_REVIEW"
    if status != "READY_FOR_REVIEW":
        add_unique(reason_codes, "HUMAN_REVIEW_REQUIRED")
    if status == "INSUFFICIENT_DATA":
        recommended_sustained = None
        recommended_burst = None
        confidence = "LOW"
        add_unique(reason_codes, "LOW_CONFIDENCE_DISCUSSION_GUARDRAIL")
    _add_envelope_reason(status, reason_codes)

    max_burst_duration = (
        profile.guardbands.max_burst_duration_minutes
        if profile and profile.guardbands.max_burst_duration_minutes is not None
        else int(config.get("max_burst_duration_minutes", 15))
    )
    guardrail = generate_sales_ops_guardrail(
        status=status,
        confidence=confidence,
        sustained_kw=recommended_sustained,
        burst_kw=recommended_burst,
        max_burst_duration_minutes=max_burst_duration,
        limiting_factor=limiting_factor,
        reason_codes=reason_codes,
        blockers=blockers,
        warnings=warnings,
    )

    observed_power = {
        "p50_kw": power_stats.observed_power_p50_kw,
        "p95_kw": power_stats.observed_power_p95_kw,
        "p99_kw": power_stats.observed_power_p99_kw,
        "max_kw": power_stats.observed_power_max_kw,
        "sustained_p95_kw": power_stats.observed_sustained_p95_kw,
        "short_burst_p99_kw": power_stats.observed_short_burst_p99_kw,
        "short_burst_max_kw": power_stats.observed_short_burst_max_kw,
        "ramp_max_kw_per_min": power_stats.observed_power_ramp_max_kw_per_min,
        "feed_a_p95_kw": power_stats.feed_a_p95_kw,
        "feed_b_p95_kw": power_stats.feed_b_p95_kw,
    }
    observed_temperature = {
        "inlet_p50_c": temp_stats.observed_inlet_p50_c,
        "inlet_p95_c": temp_stats.observed_inlet_p95_c,
        "inlet_p99_c": temp_stats.observed_inlet_p99_c,
        "inlet_max_c": temp_stats.observed_inlet_max_c,
        "top_inlet_max_c": temp_stats.observed_top_inlet_max_c,
        "middle_inlet_max_c": temp_stats.observed_middle_inlet_max_c,
        "bottom_inlet_max_c": temp_stats.observed_bottom_inlet_max_c,
        "temp_ramp_max_c_per_min": temp_stats.observed_temp_ramp_max_c_per_min,
        "hotspot_delta_top_bottom_c": temp_stats.hotspot_delta_top_bottom_c,
    }
    electrical = {
        "sustained_limit_kw": electrical_env.electrical_sustained_limit_kw,
        "burst_limit_kw": electrical_env.electrical_burst_limit_kw,
        "power_guardband_kw": electrical_env.power_guardband_kw,
        "sustained_guardrail_kw": electrical_env.electrical_guardrail_sustained_kw,
        "burst_guardrail_kw": electrical_env.electrical_guardrail_burst_kw,
        "trip_risk": electrical_env.trip_risk,
        "electrical_risk": electrical_env.electrical_risk,
        "feed_imbalance_pct": electrical_env.feed_imbalance_pct,
    }
    thermal = {
        "thermal_model_status": thermal_env.thermal_model_status,
        "slope_c_per_kw": thermal_env.thermal_slope_c_per_kw,
        "r_squared": thermal_env.thermal_model_r2,
        "best_lag_minutes": thermal_env.best_lag_minutes,
        "best_lag_r_squared": thermal_env.best_lag_r_squared,
        "predicted_warning_power_kw": thermal_env.predicted_warning_power_kw,
        "predicted_critical_power_kw": thermal_env.predicted_critical_power_kw,
        "thermal_guardrail_sustained_kw": thermal_env.thermal_guardrail_sustained_kw,
        "thermal_guardrail_burst_kw": thermal_env.thermal_guardrail_burst_kw,
        "thermal_risk": thermal_env.thermal_risk,
    }

    evidence_quality = _evidence_quality(
        alignment,
        temp_stats,
        warnings,
        missing_data,
        blockers,
        thermal_env,
        electrical_env,
    )

    return CabinetEnvelope(
        cabinet_id=alignment.cabinet_id,
        generated_at=generated_at,
        window={
            "start": isoformat_z(alignment.window_start),
            "end": isoformat_z(alignment.window_end),
            "days": alignment.window_days,
            "bucket_minutes": alignment.bucket_minutes,
        },
        envelope_status=status,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        recommended_sustained_kw=recommended_sustained,
        recommended_short_burst_kw=recommended_burst,
        max_burst_duration_minutes=max_burst_duration,
        trip_risk_threshold_kw=electrical_env.trip_risk_threshold_kw,
        thermal_risk_threshold_kw=thermal_env.thermal_risk_threshold_kw,
        limiting_factor=limiting_factor,  # type: ignore[arg-type]
        observed_power=observed_power,
        observed_temperature=observed_temperature,
        electrical=electrical,
        thermal=thermal,
        evidence_quality=evidence_quality,
        sales_ops_guardrail=guardrail,
        reason_codes=reason_codes,
        blockers=blockers,
        warnings=warnings,
        missing_data=missing_data,
        assumptions=assumptions,
    )


def build_summary(
    envelope: CabinetEnvelope,
    alignment: AlignmentResult,
    power_rows: int,
    temperature_rows: int,
) -> Summary:
    questions = recommended_questions(envelope.reason_codes, envelope.blockers)
    review_lane = envelope.review_lane or {}
    action_queue = review_lane.get("next_actions", []) if isinstance(review_lane, dict) else []
    return Summary(
        cabinet_id=envelope.cabinet_id,
        envelope_status=envelope.envelope_status,
        confidence=envelope.confidence,
        input={
            "power_rows": power_rows,
            "temperature_rows": temperature_rows,
            "aligned_buckets": alignment.coverage.aligned_buckets,
            "power_coverage_pct": alignment.coverage.power_coverage_pct,
            "temperature_coverage_pct": alignment.coverage.temperature_coverage_pct,
            "aligned_coverage_pct": alignment.coverage.aligned_coverage_pct,
        },
        review_lane={
            "lane": review_lane.get("lane"),
            "business_action": review_lane.get("business_action"),
            "decision_owner": review_lane.get("decision_owner"),
            "primary_constraint": review_lane.get("primary_constraint"),
            "evidence_gate": review_lane.get("evidence_gate"),
        }
        if review_lane
        else {},
        recommendation={
            "recommended_sustained_kw": envelope.recommended_sustained_kw,
            "recommended_short_burst_kw": envelope.recommended_short_burst_kw,
            "max_burst_duration_minutes": envelope.max_burst_duration_minutes,
            "limiting_factor": envelope.limiting_factor,
        },
        risk={
            "electrical_risk": envelope.electrical.get("electrical_risk"),
            "thermal_risk": envelope.thermal.get("thermal_risk"),
            "trip_risk": envelope.electrical.get("trip_risk"),
            "data_quality_risk": "LOW" if not envelope.missing_data and not envelope.warnings else "MEDIUM",
        },
        reason_code_counts=dict(sorted(Counter(envelope.reason_codes).items())),
        warnings=envelope.warnings,
        blockers=envelope.blockers,
        action_queue=action_queue,
        recommended_next_questions=questions,
    )
