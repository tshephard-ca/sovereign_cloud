from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from .models import CabinetEnvelope, Summary
from .portfolio import remediation_categories
from .normalize import round_float


def load_pilot_outcomes(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    outcomes: dict[str, dict[str, Any]] = {}
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            cabinet_id = (row.get("cabinet_id") or "").strip()
            if not cabinet_id:
                continue
            outcomes[cabinet_id] = {
                "facility_review_outcome": (row.get("facility_review_outcome") or "unknown").strip().lower(),
                "facility_sustained_kw": _float_or_none(row.get("facility_sustained_kw")),
                "facility_burst_kw": _float_or_none(row.get("facility_burst_kw")),
                "review_minutes": _float_or_none(row.get("review_minutes")),
                "remediation_required": (row.get("remediation_required") or "").strip().lower() in {"1", "true", "yes", "y"},
            }
    return outcomes


def _float_or_none(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _range(values: list[float | None]) -> list[float] | None:
    known = [value for value in values if value is not None]
    if not known:
        return None
    return [round_float(min(known), 3), round_float(max(known), 3)]


def _avg(values: list[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    if not known:
        return None
    return round_float(sum(known) / len(known), 3)


def build_pilot_report(
    envelopes: list[CabinetEnvelope],
    summaries: list[Summary],
    outcomes: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    outcomes = outcomes or {}
    status_counts = Counter(envelope.envelope_status for envelope in envelopes)
    review_lane_counts = Counter((envelope.review_lane or {}).get("lane", "UNKNOWN") for envelope in envelopes)
    confidence_counts = Counter(envelope.confidence for envelope in envelopes)
    limiting_counts = Counter(envelope.limiting_factor for envelope in envelopes)
    remediation_counts: Counter[str] = Counter()
    action_owner_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    coverage_values: list[float | None] = []
    sustained_values: list[float | None] = []
    burst_values: list[float | None] = []
    p95_values: list[float | None] = []
    inlet_p95_values: list[float | None] = []

    for envelope, summary in zip(envelopes, summaries):
        remediation_counts.update(remediation_categories(envelope.reason_codes, envelope.warnings, envelope.blockers, envelope.missing_data))
        for action in (envelope.review_lane or {}).get("next_actions", []):
            action_owner_counts[action.get("owner", "unknown")] += 1
        warning_counts.update(envelope.warnings)
        blocker_counts.update(envelope.blockers)
        reason_counts.update(envelope.reason_codes)
        coverage_values.append(summary.input.get("aligned_coverage_pct"))
        sustained_values.append(envelope.recommended_sustained_kw)
        burst_values.append(envelope.recommended_short_burst_kw)
        p95_values.append(envelope.observed_power.get("p95_kw"))
        inlet_p95_values.append(envelope.observed_temperature.get("inlet_p95_c"))

    outcome_counts = Counter(row.get("facility_review_outcome", "unknown") for row in outcomes.values())
    outcome_alignment = _outcome_alignment(envelopes, outcomes)
    generator_hints = _generator_hints(status_counts, limiting_counts, remediation_counts, coverage_values, p95_values, inlet_p95_values)
    business_impact = _business_impact(envelopes, outcomes)

    return {
        "schema_version": "cabinet-burst-envelope.pilot_report.v1",
        "cabinet_count": len(envelopes),
        "outcome_count": len(outcomes),
        "status_counts": dict(sorted(status_counts.items())),
        "review_lane_counts": dict(sorted(review_lane_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "limiting_factor_counts": dict(sorted(limiting_counts.items())),
        "remediation_category_counts": dict(sorted(remediation_counts.items())),
        "action_owner_counts": dict(sorted(action_owner_counts.items())),
        "telemetry_distribution": {
            "aligned_coverage_pct_range": _range(coverage_values),
            "aligned_coverage_pct_avg": _avg(coverage_values),
            "observed_power_p95_kw_range": _range(p95_values),
            "observed_inlet_p95_c_range": _range(inlet_p95_values),
        },
        "recommendation_distribution": {
            "recommended_sustained_kw_range": _range(sustained_values),
            "recommended_short_burst_kw_range": _range(burst_values),
        },
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "outcome_alignment": outcome_alignment,
        "top_reason_codes": reason_counts.most_common(20),
        "top_warnings": warning_counts.most_common(20),
        "top_blockers": blocker_counts.most_common(20),
        "generator_calibration_hints": generator_hints,
        "business_impact": business_impact,
        "data_requirements": [
            "Use normalized PDU active-kW CSV, normalized inlet-temperature CSV, and cabinet profile YAML.",
            "Outcomes are optional but should be anonymized and limited to facility review outcome, revised kW values, review time, and remediation flag.",
            "Do not include customer names, provider names, device serials, credentials, or live-control endpoints.",
        ],
    }


def _outcome_alignment(envelopes: list[CabinetEnvelope], outcomes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not outcomes:
        return {
            "available": False,
            "message": "No facility review outcome CSV was supplied.",
        }
    rows: list[dict[str, Any]] = []
    conservative_or_equal = 0
    above_facility = 0
    ready_rejected = 0
    do_not_expand_approved = 0
    matched = 0
    for envelope in envelopes:
        outcome = outcomes.get(envelope.cabinet_id)
        if not outcome:
            continue
        matched += 1
        sustained = envelope.recommended_sustained_kw
        burst = envelope.recommended_short_burst_kw
        facility_sustained = outcome.get("facility_sustained_kw")
        facility_burst = outcome.get("facility_burst_kw")
        sustained_above = sustained is not None and facility_sustained is not None and sustained > facility_sustained
        burst_above = burst is not None and facility_burst is not None and burst > facility_burst
        if sustained_above or burst_above:
            above_facility += 1
        elif facility_sustained is not None or facility_burst is not None:
            conservative_or_equal += 1
        outcome_label = outcome.get("facility_review_outcome")
        if envelope.envelope_status == "READY_FOR_REVIEW" and outcome_label in {"rejected", "deferred"}:
            ready_rejected += 1
        if envelope.envelope_status == "DO_NOT_EXPAND" and outcome_label in {"approved", "approved_with_changes"}:
            do_not_expand_approved += 1
        rows.append(
            {
                "cabinet_id": envelope.cabinet_id,
                "envelope_status": envelope.envelope_status,
                "facility_review_outcome": outcome_label,
                "recommended_sustained_kw": sustained,
                "facility_sustained_kw": facility_sustained,
                "recommended_short_burst_kw": burst,
                "facility_burst_kw": facility_burst,
                "recommendation_above_facility_outcome": sustained_above or burst_above,
            }
        )
    return {
        "available": True,
        "matched_outcomes": matched,
        "conservative_or_equal_count": conservative_or_equal,
        "recommendation_above_facility_outcome_count": above_facility,
        "ready_but_rejected_or_deferred_count": ready_rejected,
        "do_not_expand_but_approved_count": do_not_expand_approved,
        "rows": rows,
    }


def _generator_hints(
    status_counts: Counter[str],
    limiting_counts: Counter[str],
    remediation_counts: Counter[str],
    coverage_values: list[float | None],
    p95_values: list[float | None],
    inlet_p95_values: list[float | None],
) -> list[str]:
    hints: list[str] = []
    cabinet_count = max(1, sum(status_counts.values()))
    if status_counts["READY_FOR_REVIEW"] / cabinet_count < 0.2:
        hints.append("Increase clean high-confidence scenarios or calibrate ready-for-review ratio from pilot data.")
    if limiting_counts["THERMAL"] / cabinet_count < 0.1:
        hints.append("Add or up-weight thermal-limited and thermal-hotspot synthetic cases.")
    if remediation_counts["telemetry_quality"] / cabinet_count > 0.35:
        hints.append("Telemetry-quality scenarios may be overrepresented relative to a production pilot.")
    if _avg(coverage_values) is not None and (_avg(coverage_values) or 0) < 85:
        hints.append("Pilot coverage is below the default minimum; generate more gap and cadence variants.")
    if _range(p95_values):
        hints.append(f"Calibrate synthetic observed p95 power range to pilot range {_range(p95_values)} kW.")
    if _range(inlet_p95_values):
        hints.append(f"Calibrate synthetic inlet p95 range to pilot range {_range(inlet_p95_values)} C.")
    return hints


def _business_impact(envelopes: list[CabinetEnvelope], outcomes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ready = sum(1 for envelope in envelopes if envelope.envelope_status == "READY_FOR_REVIEW")
    review = sum(1 for envelope in envelopes if envelope.envelope_status == "REVIEW_REQUIRED")
    blocked = sum(1 for envelope in envelopes if envelope.envelope_status in {"DO_NOT_EXPAND", "INSUFFICIENT_DATA"})
    ready_lane = sum(1 for envelope in envelopes if (envelope.review_lane or {}).get("lane") == "READY_FOR_FACILITY_REVIEW")
    stop_lane = sum(1 for envelope in envelopes if (envelope.review_lane or {}).get("lane") == "STOP_EXPANSION_DISCUSSION")
    collect_lane = sum(1 for envelope in envelopes if (envelope.review_lane or {}).get("lane") == "COLLECT_EVIDENCE")
    remediation_lane = sum(1 for envelope in envelopes if (envelope.review_lane or {}).get("lane") == "NEEDS_REMEDIATION")
    review_minutes = [row.get("review_minutes") for row in outcomes.values() if row.get("review_minutes") is not None]
    baseline_minutes = sum(review_minutes) if review_minutes else None
    estimated_triage_minutes_saved = None
    if baseline_minutes is not None:
        estimated_triage_minutes_saved = round_float(baseline_minutes * 0.25, 1)
    return {
        "ready_for_standard_review_count": ready,
        "requires_review_count": review,
        "blocked_or_insufficient_count": blocked,
        "ready_for_facility_review_lane_count": ready_lane,
        "needs_remediation_lane_count": remediation_lane,
        "stop_expansion_discussion_lane_count": stop_lane,
        "collect_evidence_lane_count": collect_lane,
        "candidate_remediation_queue_count": blocked + review,
        "estimated_triage_minutes_saved": estimated_triage_minutes_saved,
        "impact_statement": "This is a review workflow metric, not a capacity approval or sales commitment.",
    }


def render_pilot_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Pilot Data Intake Report",
        "",
        "Review-only pilot analysis. This report is for calibration and workflow measurement, not facility approval.",
        "",
        f"- Cabinets: {report['cabinet_count']}",
        f"- Outcome rows: {report['outcome_count']}",
        f"- Status counts: {report['status_counts']}",
        f"- Review lane counts: {report.get('review_lane_counts', {})}",
        f"- Limiting factor counts: {report['limiting_factor_counts']}",
        f"- Remediation categories: {report['remediation_category_counts']}",
        f"- Action owners: {report.get('action_owner_counts', {})}",
        "",
        "## Business Impact",
    ]
    for key, value in report["business_impact"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Generator Calibration Hints"])
    hints = report.get("generator_calibration_hints") or ["No calibration hints generated."]
    lines.extend(f"- {hint}" for hint in hints)
    lines.extend(["", "## Outcome Alignment", f"- {report['outcome_alignment']}"])
    lines.extend(["", "## Data Requirements"])
    lines.extend(f"- {item}" for item in report["data_requirements"])
    return "\n".join(lines) + "\n"
