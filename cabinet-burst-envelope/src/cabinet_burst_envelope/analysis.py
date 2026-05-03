from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import load_config
from .decision import classify_review_lane
from .electrical import calculate_electrical_envelope
from .envelope import build_summary, calculate_cabinet_envelope
from .models import AlignmentResult, CabinetEnvelope, ReviewLaneDecision, Summary
from .normalize import parse_timestamp
from .statistics import compute_power_stats, compute_temperature_stats
from .thermal import calculate_thermal_envelope, fit_thermal_model
from .time_align import align_timeseries
from .validators import LoadedInputs, load_and_validate_inputs


@dataclass(frozen=True)
class CabinetAnalysisResult:
    loaded: LoadedInputs
    alignment: AlignmentResult
    envelope: CabinetEnvelope
    summary: Summary
    review_lane: ReviewLaneDecision
    generated_at: datetime


def generated_at_from(now: str | None, fallback: datetime) -> datetime:
    if now:
        return parse_timestamp(now)[0]
    return fallback if fallback.tzinfo else fallback.replace(tzinfo=UTC)


def run_cabinet_analysis(
    power: Path,
    temperature: Path,
    cabinet_profile: Path,
    config_path: Path | None,
    window_days: int,
    bucket_minutes: int,
    strict: bool,
    now: str | None,
    policy_pack: str | Path | None = None,
) -> CabinetAnalysisResult:
    thresholds = load_config(config_path, policy_pack=policy_pack)
    thresholds["default_bucket_minutes"] = bucket_minutes
    loaded = load_and_validate_inputs(power, temperature, cabinet_profile, thresholds, strict=strict)
    alignment = align_timeseries(
        loaded.power_rows,
        loaded.temperature_rows,
        loaded.cabinet_id,
        thresholds,
        window_days=window_days,
        bucket_minutes=bucket_minutes,
        now=now,
    )
    if strict and alignment.coverage.aligned_coverage_pct < float(thresholds["minimum_coverage_pct"]):
        raise ValueError("strict mode requires aligned coverage at or above minimum_coverage_pct")

    power_stats = compute_power_stats(
        alignment.buckets,
        bucket_minutes=bucket_minutes,
        sustained_window_minutes=(
            loaded.profile.guardbands.sustained_window_minutes
            if loaded.profile and loaded.profile.guardbands.sustained_window_minutes is not None
            else int(thresholds["sustained_window_minutes"])
        ),
        burst_window_minutes=(
            loaded.profile.guardbands.burst_window_minutes
            if loaded.profile and loaded.profile.guardbands.burst_window_minutes is not None
            else int(thresholds["burst_window_minutes"])
        ),
        sustained_percentile=float(thresholds["sustained_percentile"]),
        burst_percentile=float(thresholds["burst_percentile"]),
    )
    temp_stats = compute_temperature_stats(
        alignment.buckets,
        bucket_minutes=bucket_minutes,
        require_top_middle_bottom=bool(loaded.profile and loaded.profile.thermal.require_top_middle_bottom),
        hotspot_delta_top_bottom_c=float(thresholds["hotspot_top_bottom_delta_c"]),
    )
    warning_c = loaded.profile.thermal.inlet_warning_c if loaded.profile else None
    critical_c = loaded.profile.thermal.inlet_critical_c if loaded.profile else None
    thermal_model = fit_thermal_model(alignment.buckets, thresholds, warning_c, critical_c)
    electrical_env = calculate_electrical_envelope(power_stats, loaded.profile, thresholds)
    thermal_env = calculate_thermal_envelope(temp_stats, power_stats, thermal_model, loaded.profile, thresholds)
    generated_at = generated_at_from(now, alignment.window_end)
    envelope = calculate_cabinet_envelope(
        loaded.profile,
        alignment,
        power_stats,
        temp_stats,
        electrical_env,
        thermal_env,
        generated_at=generated_at,
        config=thresholds,
        input_reason_codes=loaded.reason_codes,
        input_warnings=loaded.warnings,
        input_missing_data=loaded.missing_data,
    )
    review_lane = classify_review_lane(envelope)
    envelope.review_lane = review_lane.model_dump(mode="json")
    summary = build_summary(envelope, alignment, loaded.power_input_rows, loaded.temperature_input_rows)
    return CabinetAnalysisResult(
        loaded=loaded,
        alignment=alignment,
        envelope=envelope,
        summary=summary,
        review_lane=review_lane,
        generated_at=generated_at,
    )
