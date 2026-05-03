from __future__ import annotations

from typing import Any

from .models import ActionItem, ReviewLaneDecision
from .remediation import build_action_queue, remediation_categories


CONVERSATION_BOUNDARY = (
    "Review-only preflight. This is not facility approval, not reserved capacity, "
    "not a quote, not a customer commitment, and not an operational change."
)


def _primary_constraint(envelope: Any, categories: list[str]) -> str:
    observed = set(envelope.reason_codes) | set(envelope.warnings) | set(envelope.blockers) | set(envelope.missing_data)
    if "FEED_IMBALANCE_CRITICAL" in observed or "SINGLE_FEED_SURVIVAL_RISK" in observed:
        return "feed_redundancy"
    if "profile_limits_required" in categories:
        return "profile_limits"
    if "telemetry_quality" in categories or envelope.limiting_factor == "DATA_QUALITY":
        return "data_quality"
    if "sensor_remediation" in categories:
        return "sensor_coverage"
    if envelope.limiting_factor == "THERMAL" or "thermal_limited" in categories:
        return "thermal"
    if envelope.limiting_factor == "ELECTRICAL" or "power_limited" in categories:
        return "electrical"
    if envelope.limiting_factor == "BOTH":
        return "electrical_and_thermal"
    return "unknown"


def _lane(envelope: Any, primary_constraint: str) -> str:
    if envelope.envelope_status == "READY_FOR_REVIEW":
        return "READY_FOR_FACILITY_REVIEW"
    if envelope.envelope_status == "DO_NOT_EXPAND":
        return "STOP_EXPANSION_DISCUSSION"
    if envelope.envelope_status == "INSUFFICIENT_DATA":
        return "COLLECT_EVIDENCE"
    if envelope.missing_data or envelope.confidence == "LOW" or primary_constraint in {"data_quality", "profile_limits", "sensor_coverage"}:
        return "COLLECT_EVIDENCE"
    return "NEEDS_REMEDIATION"


def _business_action(lane: str) -> str:
    return {
        "READY_FOR_FACILITY_REVIEW": "Use this packet to start a facility review conversation within the review-only guardrail.",
        "NEEDS_REMEDIATION": "Resolve the highlighted operational risk before treating the cabinet as ready for facility review.",
        "STOP_EXPANSION_DISCUSSION": "Stop the expansion discussion for this cabinet until the stop condition is resolved and the case is rerun.",
        "COLLECT_EVIDENCE": "Collect or correct the missing evidence before discussing additional bursty load.",
    }[lane]


def _owner(lane: str, primary_constraint: str) -> str:
    if lane == "READY_FOR_FACILITY_REVIEW":
        return "sales_engineering_and_facility_engineering"
    if primary_constraint in {"thermal", "electrical", "electrical_and_thermal", "feed_redundancy", "profile_limits"}:
        return "facility_engineering"
    if primary_constraint in {"data_quality", "sensor_coverage"}:
        return "operations"
    return "sales_engineering_and_operations"


def _evidence_gate(envelope: Any, lane: str) -> str:
    if envelope.missing_data:
        return "Missing evidence: " + ", ".join(envelope.missing_data)
    if lane == "READY_FOR_FACILITY_REVIEW":
        return "Required normalized telemetry and cabinet profile were sufficient for a review-only packet."
    if envelope.blockers:
        return "Hard blockers present: " + ", ".join(envelope.blockers)
    if lane == "STOP_EXPANSION_DISCUSSION":
        stop_codes = [
            code
            for code in envelope.reason_codes
            if code
            in {
                "INLET_TEMP_WARNING_OBSERVED",
                "INLET_TEMP_CRITICAL_OBSERVED",
                "CURRENT_LOAD_NEAR_OR_ABOVE_THERMAL_LIMIT",
                "HIGH_THERMAL_RISK",
                "FEED_IMBALANCE_CRITICAL",
                "SINGLE_FEED_SURVIVAL_RISK",
                "HIGH_TRIP_RISK",
            }
        ]
        return "Stop condition present: " + ", ".join(stop_codes or envelope.reason_codes[-3:])
    if envelope.warnings:
        return "Risk signals present: " + ", ".join(envelope.warnings[:5])
    return "Human review required by status or policy."


def _why_this_matters(lane: str, primary_constraint: str) -> str:
    if lane == "READY_FOR_FACILITY_REVIEW":
        return "This cabinet can move into human facility review with bounded, evidence-backed discussion numbers."
    if lane == "STOP_EXPANSION_DISCUSSION":
        return "The current evidence shows a stop condition that could turn a capacity conversation into an unsafe or wasteful commitment."
    if primary_constraint == "thermal":
        return "Thermal evidence can invalidate a power-only headroom story."
    if primary_constraint == "electrical":
        return "Electrical guardrails and trip-risk thresholds define whether additional bursty load is even discussable."
    if primary_constraint == "feed_redundancy":
        return "Feed imbalance or redundancy risk can hide inside an otherwise acceptable cabinet-level kW number."
    if primary_constraint in {"data_quality", "sensor_coverage", "profile_limits"}:
        return "The business decision cannot be cleaner than the evidence and limits behind it."
    return "The packet keeps ambiguous evidence from becoming an unsupported capacity claim."


def _decision_trace(envelope: Any, lane: str, primary_constraint: str, actions: list[ActionItem]) -> dict[str, Any]:
    return {
        "lane_rule": lane,
        "envelope_status": envelope.envelope_status,
        "confidence": envelope.confidence,
        "limiting_factor": envelope.limiting_factor,
        "primary_constraint": primary_constraint,
        "evidence_quality": envelope.evidence_quality,
        "blockers_considered": envelope.blockers,
        "warnings_considered": envelope.warnings,
        "missing_data_considered": envelope.missing_data,
        "action_ids": [action.action_id for action in actions],
    }


def classify_review_lane(envelope: Any) -> ReviewLaneDecision:
    categories = remediation_categories(envelope.reason_codes, envelope.warnings, envelope.blockers, envelope.missing_data)
    actions = build_action_queue(envelope)
    primary_constraint = _primary_constraint(envelope, categories)
    lane = _lane(envelope, primary_constraint)
    return ReviewLaneDecision(
        cabinet_id=envelope.cabinet_id,
        lane=lane,  # type: ignore[arg-type]
        envelope_status=envelope.envelope_status,
        business_action=_business_action(lane),
        decision_owner=_owner(lane, primary_constraint),
        primary_constraint=primary_constraint,
        evidence_gate=_evidence_gate(envelope, lane),
        remediation_categories=categories,
        next_actions=actions,
        conversation_boundary=CONVERSATION_BOUNDARY,
        why_this_matters=_why_this_matters(lane, primary_constraint),
        decision_trace=_decision_trace(envelope, lane, primary_constraint, actions),
        reason_codes=envelope.reason_codes,
        warnings=envelope.warnings,
        blockers=envelope.blockers,
    )
