from __future__ import annotations

from typing import Any

from .models import ActionItem


REMEDIATION_RULES = {
    "sensor_remediation": {
        "MISSING_TOP_INLET_SENSOR",
        "MISSING_MIDDLE_INLET_SENSOR",
        "MISSING_BOTTOM_INLET_SENSOR",
        "NO_VALID_INLET_SENSOR",
        "AMBIENT_SENSOR_ONLY",
    },
    "profile_limits_required": {
        "ELECTRICAL_LIMIT_MISSING",
        "THERMAL_LIMIT_MISSING",
        "TRIP_THRESHOLD_NOT_SUPPLIED",
        "BURST_LIMIT_NOT_SUPPLIED",
        "PROFILE_INVALID",
        "BURST_LIMIT_BELOW_SUSTAINED_LIMIT",
        "TRIP_THRESHOLD_BELOW_SUSTAINED_LIMIT",
        "TRIP_THRESHOLD_BELOW_BURST_LIMIT",
        "THERMAL_CRITICAL_BELOW_WARNING_LIMIT",
    },
    "power_limited": {
        "CURRENT_SUSTAINED_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL",
        "CURRENT_BURST_LOAD_EXCEEDS_ELECTRICAL_GUARDRAIL",
        "HIGH_TRIP_RISK",
        "MEDIUM_TRIP_RISK",
    },
    "thermal_limited": {
        "INLET_TEMP_WARNING_OBSERVED",
        "INLET_TEMP_CRITICAL_OBSERVED",
        "CURRENT_LOAD_NEAR_OR_ABOVE_THERMAL_LIMIT",
        "MEDIUM_THERMAL_RISK",
        "HIGH_THERMAL_RISK",
        "HOTSPOT_TOP_INLET",
    },
    "telemetry_quality": {
        "POWER_COVERAGE_LOW",
        "TEMPERATURE_COVERAGE_LOW",
        "ALIGNED_COVERAGE_LOW",
        "LONG_POWER_GAP",
        "LONG_TEMPERATURE_GAP",
        "TIMESTAMP_TIMEZONE_UNKNOWN",
        "ALL_ZERO_POWER_READINGS",
        "ESTIMATED_POWER_READINGS_PRESENT",
        "STALE_POWER_READINGS_PRESENT",
        "ESTIMATED_TEMPERATURE_READINGS_PRESENT",
        "STALE_TEMPERATURE_READINGS_PRESENT",
    },
    "feed_review": {
        "FEED_IMBALANCE_WARNING",
        "FEED_IMBALANCE_CRITICAL",
        "SINGLE_FEED_SURVIVAL_RISK",
        "SINGLE_FEED_SURVIVAL_NOT_EVALUATED",
        "REDUNDANCY_MODE_UNKNOWN",
    },
}


CATEGORY_ORDER = [
    "profile_limits_required",
    "telemetry_quality",
    "sensor_remediation",
    "power_limited",
    "feed_review",
    "thermal_limited",
]


ACTION_BY_CATEGORY: dict[str, dict[str, Any]] = {
    "sensor_remediation": {
        "action_id": "restore_inlet_sensor_coverage",
        "title": "Restore inlet sensor coverage",
        "owner": "operations",
        "priority": "HIGH",
        "evidence_needed": ["top, middle, and bottom inlet readings for the cabinet"],
        "business_impact": "Prevents a cabinet from entering a high-density review with hidden hot-spot risk.",
        "completion_signal": "Rerun assessment with required inlet sensors present and valid.",
    },
    "profile_limits_required": {
        "action_id": "confirm_site_limits",
        "title": "Confirm site-supplied cabinet limits",
        "owner": "facility_engineering",
        "priority": "HIGH",
        "evidence_needed": ["usable sustained kW", "usable burst kW", "trip-risk threshold", "thermal warning and critical thresholds"],
        "business_impact": "Stops the tool from inventing limits that should come from engineering policy.",
        "completion_signal": "Cabinet profile contains valid electrical, thermal, and guardband limits.",
    },
    "power_limited": {
        "action_id": "review_electrical_guardrail",
        "title": "Review electrical guardrail and current load",
        "owner": "facility_engineering",
        "priority": "HIGH",
        "evidence_needed": ["current sustained load", "short-burst load", "configured electrical limits", "trip-risk threshold"],
        "business_impact": "Stops expansion discussions where current or proposed load would exceed conservative electrical guardrails.",
        "completion_signal": "Electrical blocker is remediated or site limits are updated by facility engineering.",
    },
    "feed_review": {
        "action_id": "review_feed_balance_and_redundancy",
        "title": "Review feed balance and redundancy assumptions",
        "owner": "facility_engineering",
        "priority": "HIGH",
        "evidence_needed": ["A/B feed p95 values", "redundancy mode", "single-feed survival policy"],
        "business_impact": "Catches cabinets where apparent cabinet-level headroom may hide feed or redundancy risk.",
        "completion_signal": "Feed imbalance and redundancy assumptions are accepted or corrected in the profile.",
    },
    "thermal_limited": {
        "action_id": "remediate_thermal_constraint",
        "title": "Remediate thermal constraint before additional load",
        "owner": "facility_engineering",
        "priority": "HIGH",
        "evidence_needed": ["max inlet temperature", "top/middle/bottom inlet spread", "thermal warning threshold", "post-remediation telemetry"],
        "business_impact": "Prevents a power-only capacity conversation from overlooking airflow or cooling constraints.",
        "completion_signal": "Rerun assessment after airflow, cabling, containment, or cooling remediation.",
    },
    "telemetry_quality": {
        "action_id": "repair_telemetry_quality",
        "title": "Repair telemetry coverage or quality",
        "owner": "operations",
        "priority": "HIGH",
        "evidence_needed": ["continuous power readings", "continuous inlet-temperature readings", "timestamp quality", "coverage above configured threshold"],
        "business_impact": "Avoids spending facility review time on a cabinet where evidence cannot support a clear discussion lane.",
        "completion_signal": "Rerun assessment with adequate aligned coverage and trustworthy readings.",
    },
}


READY_ACTION = ActionItem(
    action_id="start_facility_review_packet",
    title="Start facility review with this packet",
    owner="sales_engineering",
    priority="LOW",
    reason_codes=["ENVELOPE_READY_FOR_REVIEW"],
    evidence_needed=["decision JSON", "envelope JSON", "aligned telemetry CSV", "guardrail report"],
    business_impact="Moves a qualified cabinet into human review without presenting the output as approval or reserved capacity.",
    completion_signal="Facility engineering accepts the packet for its own review workflow.",
)


GENERIC_REVIEW_ACTION = ActionItem(
    action_id="human_review_of_uncategorized_signal",
    title="Review uncategorized risk signal",
    owner="sales_engineering_and_operations",
    priority="MEDIUM",
    reason_codes=["HUMAN_REVIEW_REQUIRED"],
    evidence_needed=["reason codes", "warnings", "blockers", "input files"],
    business_impact="Keeps ambiguous evidence from being treated as a clean capacity conversation.",
    completion_signal="Reviewer identifies whether the case needs remediation, more evidence, or facility review.",
)


def remediation_categories(
    reason_codes: list[str],
    warnings: list[str],
    blockers: list[str],
    missing_data: list[str] | None = None,
) -> list[str]:
    observed = set(reason_codes) | set(warnings) | set(blockers) | set(missing_data or [])
    categories = [category for category in CATEGORY_ORDER if observed & REMEDIATION_RULES[category]]
    return categories


def build_action_queue(envelope: Any) -> list[ActionItem]:
    observed = set(envelope.reason_codes) | set(envelope.warnings) | set(envelope.blockers) | set(envelope.missing_data)
    categories = remediation_categories(envelope.reason_codes, envelope.warnings, envelope.blockers, envelope.missing_data)
    actions: list[ActionItem] = []
    for category in categories:
        template = ACTION_BY_CATEGORY[category]
        source_codes = sorted(observed & REMEDIATION_RULES[category])
        priority = "HIGH" if set(source_codes) & set(envelope.blockers) else template["priority"]
        actions.append(
            ActionItem(
                action_id=template["action_id"],
                title=template["title"],
                owner=template["owner"],
                priority=priority,
                reason_codes=source_codes,
                evidence_needed=list(template["evidence_needed"]),
                business_impact=template["business_impact"],
                completion_signal=template["completion_signal"],
            )
        )
    if not actions and envelope.envelope_status == "READY_FOR_REVIEW":
        actions.append(READY_ACTION)
    elif not actions:
        actions.append(GENERIC_REVIEW_ACTION)
    return actions
