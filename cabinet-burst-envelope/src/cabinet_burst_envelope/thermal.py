from __future__ import annotations

from .models import CabinetProfile, PowerStats, TemperatureStats, ThermalEnvelope, ThermalModelResult, TimeBucket
from .normalize import add_unique, round_float


def _linear_regression(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, mean_y, 0.0
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in points)
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_total = sum((y - mean_y) ** 2 for y in ys)
    ss_residual = sum((y - (intercept + slope * x)) ** 2 for x, y in points)
    r_squared = 0.0 if ss_total == 0 else max(0.0, 1.0 - ss_residual / ss_total)
    return slope, intercept, r_squared


def _lagged_points(buckets: list[TimeBucket], lag_buckets: int) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for index in range(lag_buckets, len(buckets)):
        power_bucket = buckets[index - lag_buckets]
        temp_bucket = buckets[index]
        if power_bucket.cabinet_power_kw is not None and temp_bucket.max_inlet_temp_c is not None:
            points.append((float(power_bucket.cabinet_power_kw), float(temp_bucket.max_inlet_temp_c)))
    return points


def _best_lag(buckets: list[TimeBucket], bucket_minutes: int) -> tuple[int, float | None]:
    best_lag = 0
    best_r2: float | None = None
    for lag_minutes in (0, bucket_minutes, bucket_minutes * 2, bucket_minutes * 3, bucket_minutes * 6, bucket_minutes * 12):
        points = _lagged_points(buckets, lag_minutes // bucket_minutes)
        if len(points) < 12:
            continue
        slope, _intercept, r_squared = _linear_regression(points)
        if slope <= 0:
            continue
        if best_r2 is None or r_squared > best_r2:
            best_lag = lag_minutes
            best_r2 = r_squared
    return best_lag, best_r2


def fit_thermal_model(
    buckets: list[TimeBucket],
    config: dict,
    inlet_warning_c: float | None = None,
    inlet_critical_c: float | None = None,
) -> ThermalModelResult:
    points = [
        (float(bucket.cabinet_power_kw), float(bucket.max_inlet_temp_c))
        for bucket in buckets
        if bucket.cabinet_power_kw is not None and bucket.max_inlet_temp_c is not None
    ]
    reason_codes: list[str] = []
    warnings: list[str] = []
    if len(points) < 12:
        add_unique(reason_codes, "THERMAL_MODEL_UNUSABLE")
        add_unique(warnings, "THERMAL_MODEL_UNUSABLE")
        return ThermalModelResult(
            thermal_model_status="UNUSABLE",
            sample_count=len(points),
            best_lag_minutes=0,
            best_lag_r_squared=None,
            reason_codes=reason_codes,
            warnings=warnings,
        )

    powers = [point[0] for point in points]
    temps = [point[1] for point in points]
    power_range = max(powers) - min(powers)
    temp_range = max(temps) - min(temps)
    mean_power = sum(powers) / len(powers)
    power_range_pct = (power_range / mean_power * 100.0) if mean_power else 0.0
    slope, intercept, r_squared = _linear_regression(points)
    bucket_minutes = int(config.get("default_bucket_minutes", 5))
    best_lag_minutes, best_lag_r2 = _best_lag(buckets, bucket_minutes)

    usable = True
    if (
        power_range < float(config["min_power_variation_kw_for_thermal_model"])
        and power_range_pct < float(config["min_power_variation_pct_for_thermal_model"])
    ):
        usable = False
        add_unique(reason_codes, "POWER_VARIATION_TOO_LOW_FOR_THERMAL_MODEL")
        add_unique(warnings, "POWER_VARIATION_TOO_LOW_FOR_THERMAL_MODEL")
    if temp_range < float(config["min_temp_variation_c_for_thermal_model"]):
        usable = False
        add_unique(reason_codes, "TEMP_VARIATION_TOO_LOW_FOR_THERMAL_MODEL")
        add_unique(warnings, "TEMP_VARIATION_TOO_LOW_FOR_THERMAL_MODEL")
    if slope < float(config["min_positive_temp_slope_c_per_kw"]):
        usable = False
        add_unique(reason_codes, "THERMAL_SLOPE_NOT_POSITIVE")
        add_unique(warnings, "THERMAL_SLOPE_NOT_POSITIVE")
    if r_squared < float(config["min_thermal_model_r2"]):
        usable = False
        add_unique(reason_codes, "THERMAL_MODEL_LOW_R2")
        add_unique(warnings, "THERMAL_MODEL_LOW_R2")

    if usable:
        add_unique(reason_codes, "THERMAL_MODEL_USABLE")
    else:
        add_unique(reason_codes, "THERMAL_MODEL_UNUSABLE")
        add_unique(warnings, "THERMAL_MODEL_UNUSABLE")

    predicted_warning = None
    predicted_critical = None
    if slope > 0:
        if inlet_warning_c is not None:
            predicted_warning = (inlet_warning_c - intercept) / slope
        if inlet_critical_c is not None:
            predicted_critical = (inlet_critical_c - intercept) / slope

    return ThermalModelResult(
        thermal_model_status="USABLE" if usable else "UNUSABLE",
        slope_c_per_kw=round_float(slope, 6),
        intercept_c=round_float(intercept, 6),
        r_squared=round_float(r_squared, 6),
        best_lag_minutes=best_lag_minutes,
        best_lag_r_squared=round_float(best_lag_r2, 6),
        sample_count=len(points),
        power_range_kw=round_float(power_range, 3),
        temp_range_c=round_float(temp_range, 3),
        predicted_warning_power_kw=round_float(predicted_warning, 3),
        predicted_critical_power_kw=round_float(predicted_critical, 3),
        reason_codes=reason_codes,
        warnings=warnings,
    )


def calculate_thermal_envelope(
    temp_stats: TemperatureStats,
    power_stats: PowerStats,
    model: ThermalModelResult,
    profile: CabinetProfile | None,
    config: dict,
) -> ThermalEnvelope:
    reason_codes = list(model.reason_codes)
    warnings = list(model.warnings)
    blockers: list[str] = []
    thermal = profile.thermal if profile else None
    warning_c = thermal.inlet_warning_c if thermal else None
    critical_c = thermal.inlet_critical_c if thermal else None

    if warning_c is None or critical_c is None:
        add_unique(reason_codes, "THERMAL_LIMIT_MISSING")
        add_unique(warnings, "THERMAL_LIMIT_MISSING")
    else:
        add_unique(reason_codes, "THERMAL_LIMIT_PRESENT")

    for code in temp_stats.reason_codes:
        add_unique(reason_codes, code)
        if code.startswith("MISSING_"):
            add_unique(warnings, code)

    temp_guardband_c = (
        profile.guardbands.temp_headroom_c
        if profile and profile.guardbands.temp_headroom_c is not None
        else float(config["default_temp_headroom_c"])
    )
    add_unique(reason_codes, "THERMAL_GUARDBAND_APPLIED")

    thermal_headroom_c = None
    if warning_c is not None and temp_stats.observed_inlet_p95_c is not None:
        thermal_headroom_c = warning_c - temp_stats.observed_inlet_p95_c

    max_extrapolation_kw = (
        thermal.max_thermal_extrapolation_kw
        if thermal and thermal.max_thermal_extrapolation_kw is not None
        else float(config["max_default_thermal_extrapolation_kw"])
    )
    observed_max_power = power_stats.observed_power_max_kw

    sustained_guardrail = None
    burst_guardrail = None
    thermal_risk_threshold_kw = None
    if model.thermal_model_status == "USABLE" and model.slope_c_per_kw and model.intercept_c and warning_c is not None:
        effective_warning = warning_c - temp_guardband_c
        sustained_raw = (effective_warning - model.intercept_c) / model.slope_c_per_kw
        cap = None if observed_max_power is None else observed_max_power + max_extrapolation_kw
        if cap is not None and sustained_raw > cap:
            sustained_raw = cap
            add_unique(reason_codes, "THERMAL_EXTRAPOLATION_CAPPED")
        sustained_guardrail = max(0.0, sustained_raw)

        if critical_c is not None:
            effective_critical = critical_c - temp_guardband_c
            burst_raw = (effective_critical - model.intercept_c) / model.slope_c_per_kw
            if model.predicted_critical_power_kw is not None:
                burst_raw = min(burst_raw, model.predicted_critical_power_kw)
            if cap is not None and burst_raw > cap:
                burst_raw = cap
                add_unique(reason_codes, "THERMAL_EXTRAPOLATION_CAPPED")
            burst_guardrail = max(0.0, burst_raw)
        thermal_risk_threshold_kw = model.predicted_warning_power_kw

    risk = "UNKNOWN"
    if temp_stats.observed_inlet_max_c is None:
        add_unique(reason_codes, "THERMAL_RISK_UNKNOWN")
    elif warning_c is None or critical_c is None:
        add_unique(reason_codes, "THERMAL_RISK_UNKNOWN")
    else:
        risk = "LOW"
        if temp_stats.observed_inlet_max_c >= critical_c:
            risk = "HIGH"
            add_unique(reason_codes, "INLET_TEMP_CRITICAL_OBSERVED", "HIGH_THERMAL_RISK")
            add_unique(blockers, "INLET_TEMP_CRITICAL_OBSERVED")
        elif temp_stats.observed_inlet_p95_c is not None and temp_stats.observed_inlet_p95_c >= warning_c:
            risk = "HIGH"
            add_unique(reason_codes, "INLET_TEMP_WARNING_OBSERVED", "HIGH_THERMAL_RISK")
            add_unique(warnings, "INLET_TEMP_WARNING_OBSERVED")
        elif (
            temp_stats.observed_inlet_p95_c is not None
            and temp_stats.observed_inlet_p95_c >= warning_c - float(config["medium_thermal_risk_margin_c"])
        ) or temp_stats.observed_inlet_max_c >= critical_c - float(config["medium_thermal_risk_margin_c"]):
            risk = "MEDIUM"
            add_unique(reason_codes, "MEDIUM_THERMAL_RISK")
            add_unique(warnings, "MEDIUM_THERMAL_RISK")

        if "MISSING_TOP_INLET_SENSOR" in reason_codes and risk == "LOW":
            risk = "MEDIUM"
            add_unique(reason_codes, "MEDIUM_THERMAL_RISK")
            add_unique(warnings, "MISSING_TOP_INLET_SENSOR", "MEDIUM_THERMAL_RISK")
        if "HOTSPOT_TOP_INLET" in reason_codes and risk == "LOW":
            risk = "MEDIUM"
            add_unique(reason_codes, "MEDIUM_THERMAL_RISK")
            add_unique(warnings, "MEDIUM_THERMAL_RISK")

    if (
        model.thermal_model_status == "USABLE"
        and model.predicted_warning_power_kw is not None
        and power_stats.observed_power_p95_kw is not None
        and model.predicted_warning_power_kw <= power_stats.observed_power_p95_kw
    ):
        risk = "HIGH"
        add_unique(reason_codes, "CURRENT_LOAD_NEAR_OR_ABOVE_THERMAL_LIMIT", "HIGH_THERMAL_RISK")

    return ThermalEnvelope(
        thermal_model_status=model.thermal_model_status,
        thermal_slope_c_per_kw=model.slope_c_per_kw,
        thermal_model_r2=model.r_squared,
        best_lag_minutes=model.best_lag_minutes,
        best_lag_r_squared=model.best_lag_r_squared,
        predicted_warning_power_kw=model.predicted_warning_power_kw,
        predicted_critical_power_kw=model.predicted_critical_power_kw,
        thermal_guardrail_sustained_kw=round_float(sustained_guardrail, 3),
        thermal_guardrail_burst_kw=round_float(burst_guardrail, 3),
        thermal_risk_threshold_kw=round_float(thermal_risk_threshold_kw, 3),
        thermal_headroom_c=round_float(thermal_headroom_c, 3),
        thermal_risk=risk,  # type: ignore[arg-type]
        thermal_reason_codes=reason_codes,
        warnings=warnings,
        blockers=blockers,
    )
