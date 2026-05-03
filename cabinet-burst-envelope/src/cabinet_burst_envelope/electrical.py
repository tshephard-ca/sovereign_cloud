from __future__ import annotations

from .models import CabinetProfile, ElectricalEnvelope, PowerStats
from .normalize import add_unique, round_float


def calculate_electrical_envelope(
    power_stats: PowerStats,
    profile: CabinetProfile | None,
    config: dict,
) -> ElectricalEnvelope:
    reason_codes: list[str] = []
    warnings: list[str] = []
    blockers: list[str] = []
    electrical = profile.electrical if profile else None
    guardbands = profile.guardbands if profile else None

    sustained_limit = electrical.usable_sustained_kw if electrical else None
    burst_limit = electrical.usable_burst_kw if electrical else None
    trip_threshold = electrical.trip_risk_kw if electrical else None

    if sustained_limit is None:
        add_unique(reason_codes, "ELECTRICAL_LIMIT_MISSING")
        add_unique(blockers, "ELECTRICAL_LIMIT_MISSING")
    else:
        add_unique(reason_codes, "ELECTRICAL_LIMIT_PRESENT")

    if burst_limit is None:
        burst_limit = sustained_limit
        add_unique(reason_codes, "BURST_LIMIT_NOT_SUPPLIED")
        add_unique(warnings, "BURST_LIMIT_NOT_SUPPLIED")
    else:
        add_unique(reason_codes, "BURST_LIMIT_PRESENT")

    if trip_threshold is None:
        add_unique(reason_codes, "TRIP_THRESHOLD_NOT_SUPPLIED")
        add_unique(warnings, "TRIP_THRESHOLD_NOT_SUPPLIED")
    else:
        add_unique(reason_codes, "TRIP_THRESHOLD_PRESENT")

    if electrical and electrical.redundancy_mode == "UNKNOWN":
        add_unique(reason_codes, "REDUNDANCY_MODE_UNKNOWN")
        add_unique(warnings, "REDUNDANCY_MODE_UNKNOWN")

    power_guardband_kw = None
    sustained_guardrail = None
    burst_guardrail = None
    if sustained_limit is not None:
        headroom_pct = (
            guardbands.power_headroom_pct
            if guardbands and guardbands.power_headroom_pct is not None
            else float(config["default_power_headroom_pct"])
        )
        min_headroom = (
            guardbands.min_power_headroom_kw
            if guardbands and guardbands.min_power_headroom_kw is not None
            else float(config["default_min_power_headroom_kw"])
        )
        power_guardband_kw = max(sustained_limit * headroom_pct / 100.0, min_headroom)
        sustained_guardrail = sustained_limit - power_guardband_kw
        add_unique(reason_codes, "ELECTRICAL_GUARDBAND_APPLIED")
    if burst_limit is not None and power_guardband_kw is not None:
        burst_guardrail = burst_limit - power_guardband_kw

    electrical_risk = "LOW" if sustained_limit is not None else "UNKNOWN"
    if sustained_guardrail is not None and power_stats.observed_sustained_p95_kw is not None:
        if power_stats.observed_sustained_p95_kw > sustained_guardrail:
            electrical_risk = "HIGH"
            add_unique(reason_codes, "CURRENT_SUSTAINED_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL")
            add_unique(blockers, "CURRENT_SUSTAINED_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL")
    if burst_guardrail is not None and power_stats.observed_short_burst_p99_kw is not None:
        if power_stats.observed_short_burst_p99_kw > burst_guardrail:
            electrical_risk = "HIGH"
            add_unique(reason_codes, "CURRENT_BURST_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL")
            add_unique(blockers, "CURRENT_BURST_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL")

    trip_risk = "UNKNOWN"
    observed_for_trip = power_stats.observed_short_burst_p99_kw or power_stats.observed_power_max_kw
    if trip_threshold is not None and observed_for_trip is not None:
        trip_risk = "LOW"
        margin = trip_threshold - observed_for_trip
        if margin <= float(config["high_trip_risk_margin_kw"]):
            trip_risk = "HIGH"
            electrical_risk = "HIGH"
            add_unique(reason_codes, "HIGH_TRIP_RISK")
            add_unique(blockers, "HIGH_TRIP_RISK")
        elif margin <= float(config["medium_trip_risk_margin_kw"]):
            trip_risk = "MEDIUM"
            if electrical_risk == "LOW":
                electrical_risk = "MEDIUM"
            add_unique(reason_codes, "MEDIUM_TRIP_RISK")
            add_unique(warnings, "MEDIUM_TRIP_RISK")

    if power_stats.feed_imbalance_pct is not None:
        if power_stats.feed_imbalance_pct >= float(config["feed_imbalance_critical_pct"]):
            add_unique(reason_codes, "FEED_IMBALANCE_CRITICAL")
            add_unique(blockers, "FEED_IMBALANCE_CRITICAL")
            electrical_risk = "HIGH"
        elif power_stats.feed_imbalance_pct >= float(config["feed_imbalance_warning_pct"]):
            add_unique(reason_codes, "FEED_IMBALANCE_WARNING")
            add_unique(warnings, "FEED_IMBALANCE_WARNING")
            if electrical_risk == "LOW":
                electrical_risk = "MEDIUM"

    if electrical and electrical.redundancy_mode == "A_B_REDUNDANT":
        if electrical.require_single_feed_survival:
            feed_limits = {limit.feed_id.upper(): limit for limit in electrical.feed_limits}
            if not feed_limits:
                add_unique(reason_codes, "SINGLE_FEED_SURVIVAL_NOT_EVALUATED")
                add_unique(warnings, "SINGLE_FEED_SURVIVAL_NOT_EVALUATED")
            else:
                total = power_stats.observed_sustained_p95_kw or power_stats.observed_power_p95_kw
                if total is not None:
                    for feed_id, limit in feed_limits.items():
                        if limit.usable_sustained_kw is not None and total > limit.usable_sustained_kw:
                            add_unique(reason_codes, "SINGLE_FEED_SURVIVAL_RISK")
                            add_unique(blockers, "SINGLE_FEED_SURVIVAL_RISK")
                            electrical_risk = "HIGH"
                            break
        else:
            add_unique(reason_codes, "SINGLE_FEED_SURVIVAL_NOT_EVALUATED")
            add_unique(warnings, "SINGLE_FEED_SURVIVAL_NOT_EVALUATED")

    observed_sustained = power_stats.observed_sustained_p95_kw
    observed_burst = power_stats.observed_short_burst_p99_kw
    return ElectricalEnvelope(
        electrical_sustained_limit_kw=round_float(sustained_limit, 3),
        electrical_burst_limit_kw=round_float(burst_limit, 3),
        trip_risk_threshold_kw=round_float(trip_threshold, 3),
        power_guardband_kw=round_float(power_guardband_kw, 3),
        electrical_guardrail_sustained_kw=round_float(sustained_guardrail, 3),
        electrical_guardrail_burst_kw=round_float(burst_guardrail, 3),
        electrical_headroom_sustained_kw=round_float(sustained_limit - observed_sustained, 3) if sustained_limit is not None and observed_sustained is not None else None,
        electrical_headroom_burst_kw=round_float(burst_limit - observed_burst, 3) if burst_limit is not None and observed_burst is not None else None,
        electrical_risk=electrical_risk,  # type: ignore[arg-type]
        trip_risk=trip_risk,  # type: ignore[arg-type]
        feed_imbalance_pct=power_stats.feed_imbalance_pct,
        electrical_reason_codes=reason_codes,
        warnings=warnings,
        blockers=blockers,
    )
