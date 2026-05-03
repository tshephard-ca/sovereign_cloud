from __future__ import annotations

from .models import SalesOpsGuardrail


QUESTION_BY_CODE = {
    "POWER_DATA_MISSING": "Which PDU or normalized export should provide cabinet-level active kW?",
    "TEMPERATURE_DATA_MISSING": "Which inlet sensors measure top, middle, and bottom front-of-rack temperatures?",
    "ELECTRICAL_LIMIT_MISSING": "What site-approved sustained kW limit should be used for this cabinet?",
    "BURST_LIMIT_NOT_SUPPLIED": "Is short-burst operation allowed above the sustained limit, and for how many minutes?",
    "TRIP_THRESHOLD_NOT_SUPPLIED": "What threshold should be treated as trip-risk for review purposes?",
    "THERMAL_MODEL_UNUSABLE": "Was there enough power variation during the window to estimate thermal sensitivity?",
    "MISSING_TOP_INLET_SENSOR": "Can top inlet sensing be added or repaired before approving higher-density loads?",
    "HOTSPOT_TOP_INLET": "Is the top inlet hot spot caused by airflow, blanking, cabling, neighboring exhaust, or sensor placement?",
    "FEED_IMBALANCE_WARNING": "Is A/B feed imbalance expected, and does it affect redundancy assumptions?",
    "FEED_IMBALANCE_CRITICAL": "What feed-balancing or redundancy remediation is required before additional load is discussed?",
    "SINGLE_FEED_SURVIVAL_RISK": "Can the cabinet survive the configured single-feed scenario at observed load?",
    "SINGLE_FEED_SURVIVAL_NOT_EVALUATED": "Should single-feed survival be required for this cabinet profile?",
    "REDUNDANCY_MODE_UNKNOWN": "What redundancy mode should be used for this cabinet review?",
    "CURRENT_SUSTAINED_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL": "Should the existing cabinet load be reviewed before adding any new equipment?",
    "CURRENT_BURST_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL": "Should current burst behavior be remediated before additional bursty load is discussed?",
    "CURRENT_LOAD_NEAR_OR_ABOVE_THERMAL_LIMIT": "Should airflow or cooling remediation be completed before additional load is placed?",
    "ALIGNED_COVERAGE_TOO_LOW": "Can power and inlet-temperature exports be collected for a longer overlapping window?",
    "POWER_COVERAGE_LOW": "Can the PDU export provide continuous active-kW readings for the analysis window?",
    "TEMPERATURE_COVERAGE_LOW": "Can inlet-temperature telemetry coverage be restored for the analysis window?",
    "LONG_POWER_GAP": "What caused the long power telemetry gap, and can the export be regenerated?",
    "LONG_TEMPERATURE_GAP": "What caused the long temperature telemetry gap, and can the export be regenerated?",
    "PROFILE_INVALID": "Which cabinet profile limit is invalid and needs correction before review?",
    "THERMAL_LIMIT_MISSING": "What inlet warning and critical temperatures should be used for this cabinet?",
    "INLET_TEMP_WARNING_OBSERVED": "What airflow or cooling check is required because inlet temperature reached warning level?",
    "INLET_TEMP_CRITICAL_OBSERVED": "What immediate thermal remediation is required before this cabinet is reconsidered?",
    "ENVELOPE_DO_NOT_EXPAND": "What remediation is required before this cabinet can be reconsidered for additional bursty load?",
    "ENVELOPE_INSUFFICIENT_DATA": "Which missing evidence must be collected before a cabinet envelope can be calculated?",
    "LOW_CONFIDENCE_DISCUSSION_GUARDRAIL": "What evidence would raise confidence before this cabinet enters a capacity conversation?",
    "DO_NOT_EXPAND": "What remediation is required before this cabinet can be reconsidered for additional bursty load?",
}


def recommended_questions(reason_codes: list[str], blockers: list[str]) -> list[str]:
    out: list[str] = []
    for code in list(blockers) + list(reason_codes):
        question = QUESTION_BY_CODE.get(code)
        if question and question not in out:
            out.append(question)
    if not out:
        out.append("What facility engineering review is required before using this review-only envelope operationally?")
    return out


def _kw_text(value: float | None) -> str:
    return "unknown kW" if value is None else f"{value:.1f} kW"


def generate_sales_ops_guardrail(
    status: str,
    confidence: str,
    sustained_kw: float | None,
    burst_kw: float | None,
    max_burst_duration_minutes: int | None,
    limiting_factor: str,
    reason_codes: list[str],
    blockers: list[str],
    warnings: list[str],
) -> SalesOpsGuardrail:
    questions = recommended_questions(reason_codes, blockers)
    next_step = questions[0]
    burst_duration = max_burst_duration_minutes if max_burst_duration_minutes is not None else 0

    if blockers or status == "DO_NOT_EXPAND":
        details: list[str] = []
        if "CURRENT_BURST_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL" in reason_codes:
            details.append("current observed burst load exceeds the configured burst guardrail")
        if "CURRENT_SUSTAINED_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL" in reason_codes:
            details.append("current observed sustained load exceeds the configured sustained guardrail")
        if "INLET_TEMP_WARNING_OBSERVED" in reason_codes:
            details.append("inlet temperature has reached the warning threshold")
        if "INLET_TEMP_CRITICAL_OBSERVED" in reason_codes:
            details.append("inlet temperature has reached the critical threshold")
        if "CURRENT_LOAD_NEAR_OR_ABOVE_THERMAL_LIMIT" in reason_codes:
            details.append("current load is near or above the modeled thermal review limit")
        if "HIGH_THERMAL_RISK" in reason_codes:
            details.append("thermal risk is high from the observed evidence")
        if "HIGH_TRIP_RISK" in reason_codes:
            details.append("current load is near the trip-risk threshold from the user profile")
        reason = ", and ".join(details) if details else "one or more stop-expansion signals require human review"
        text = f"Review-only do not expand: {reason}. Do not add bursty load until facility engineering review resolves the issue."
    elif status == "INSUFFICIENT_DATA":
        text = "Review-only result: insufficient data to calculate a credible cabinet power envelope. Treat any kW value as unavailable until the missing inputs are corrected."
    elif confidence == "LOW":
        thermal_note = ""
        if "THERMAL_MODEL_UNUSABLE" in reason_codes:
            thermal_note = " Thermal model is unusable from the observed window."
        text = (
            f"Review-only discussion guardrail: use no more than {_kw_text(sustained_kw)} sustained "
            f"and {_kw_text(burst_kw)} short burst for up to {burst_duration} minutes pending facility review."
            f"{thermal_note}"
        )
    elif status == "REVIEW_REQUIRED":
        thermal_note = ""
        if "THERMAL_MODEL_UNUSABLE" in reason_codes:
            thermal_note = " Thermal confidence is limited because the simple thermal model is unusable."
        text = (
            f"Review-only guardrail: use {_kw_text(sustained_kw)} sustained and {_kw_text(burst_kw)} short burst "
            f"for up to {burst_duration} minutes as a discussion limit pending facility review.{thermal_note}"
        )
    else:
        text = (
            f"Review-only guardrail: this cabinet appears suitable for review at up to {_kw_text(sustained_kw)} sustained "
            f"and {_kw_text(burst_kw)} short burst for up to {burst_duration} minutes, subject to facility approval. "
            f"{limiting_factor.title().replace('_', ' ')} is the limiting factor. Do not sell above {_kw_text(sustained_kw)} sustained without engineering review."
        )

    return SalesOpsGuardrail(
        status=status,  # type: ignore[arg-type]
        text=text,
        recommended_next_step=next_step,
    )
