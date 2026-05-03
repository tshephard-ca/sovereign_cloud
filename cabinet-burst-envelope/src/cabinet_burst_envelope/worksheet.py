from __future__ import annotations

from .guardrail import recommended_questions
from .models import CabinetEnvelope
from .report import DATA_HONESTY_CAVEATS, display


def render_facility_review_worksheet(envelope: CabinetEnvelope) -> str:
    questions = recommended_questions(envelope.reason_codes, envelope.blockers)
    review_lane = envelope.review_lane or {}
    lines = [
        "# Facility Engineering Review Worksheet",
        "",
        "This worksheet is for human facility engineering review. It is not an approval, live control action, or capacity contract.",
        "",
        "## Review Lane",
        "",
        f"- Review lane: {display(review_lane.get('lane'))}",
        f"- Business action: {display(review_lane.get('business_action'))}",
        f"- Decision owner: {display(review_lane.get('decision_owner'))}",
        f"- Primary constraint: {display(review_lane.get('primary_constraint'))}",
        f"- Evidence gate: {display(review_lane.get('evidence_gate'))}",
        "",
        "## Proposed Review Envelope",
        "",
        f"- Cabinet ID: {envelope.cabinet_id}",
        f"- Envelope status: {envelope.envelope_status}",
        f"- Confidence: {envelope.confidence}",
        f"- Evidence quality: {envelope.evidence_quality.get('score')} ({envelope.evidence_quality.get('band')})",
        f"- Proposed sustained kW: {display(envelope.recommended_sustained_kw)}",
        f"- Proposed short-burst kW: {display(envelope.recommended_short_burst_kw)}",
        f"- Maximum burst duration minutes: {display(envelope.max_burst_duration_minutes)}",
        f"- Limiting factor: {envelope.limiting_factor}",
        "",
        "## Evidence Summary",
        "",
        f"- Observed sustained p95 kW: {display(envelope.observed_power.get('sustained_p95_kw'))}",
        f"- Observed short-burst p99 kW: {display(envelope.observed_power.get('short_burst_p99_kw'))}",
        f"- Observed inlet p95 C: {display(envelope.observed_temperature.get('inlet_p95_c'))}",
        f"- Observed inlet max C: {display(envelope.observed_temperature.get('inlet_max_c'))}",
        f"- Trip-risk threshold kW: {display(envelope.trip_risk_threshold_kw)}",
        f"- Thermal-risk threshold kW: {display(envelope.thermal_risk_threshold_kw)}",
        "",
        "## Reason Codes",
        "",
    ]
    lines.extend(f"- {code}" for code in envelope.reason_codes or ["None"])
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- {code}" for code in envelope.blockers or ["None"])
    lines.extend(["", "## Action Queue", ""])
    for action in review_lane.get("next_actions", []) or []:
        lines.append(f"- {action.get('priority', 'UNKNOWN')}: {action.get('title')} ({action.get('owner')})")
    if not review_lane.get("next_actions"):
        lines.append("- None")
    lines.extend(["", "## Questions For Review", ""])
    lines.extend(f"- {question}" for question in questions)
    lines.extend(
        [
            "",
            "## Human Signoff",
            "",
            "- Facility reviewer:",
            "- Review date:",
            "- Facility response: accept for next review / revise packet / reject packet",
            "- Revised sustained kW:",
            "- Revised short-burst kW:",
            "- Required remediation:",
            "- Notes:",
            "",
            "## Data Honesty Caveats",
            "",
        ]
    )
    lines.extend(f"- {caveat}" for caveat in DATA_HONESTY_CAVEATS)
    lines.append("")
    return "\n".join(lines)
