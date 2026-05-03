from __future__ import annotations

from typing import Any

from .models import CabinetEnvelope


def _delta(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return round(current - previous, 3)


def compare_envelopes(previous: CabinetEnvelope, current: CabinetEnvelope) -> dict[str, Any]:
    previous_codes = set(previous.reason_codes)
    current_codes = set(current.reason_codes)
    previous_warnings = set(previous.warnings)
    current_warnings = set(current.warnings)
    previous_blockers = set(previous.blockers)
    current_blockers = set(current.blockers)
    return {
        "schema_version": "cabinet-burst-envelope.drift.v1",
        "cabinet_id_previous": previous.cabinet_id,
        "cabinet_id_current": current.cabinet_id,
        "status_previous": previous.envelope_status,
        "status_current": current.envelope_status,
        "confidence_previous": previous.confidence,
        "confidence_current": current.confidence,
        "recommended_sustained_delta_kw": _delta(current.recommended_sustained_kw, previous.recommended_sustained_kw),
        "recommended_short_burst_delta_kw": _delta(current.recommended_short_burst_kw, previous.recommended_short_burst_kw),
        "thermal_slope_delta_c_per_kw": _delta(current.thermal.get("slope_c_per_kw"), previous.thermal.get("slope_c_per_kw")),
        "feed_imbalance_delta_pct": _delta(current.electrical.get("feed_imbalance_pct"), previous.electrical.get("feed_imbalance_pct")),
        "inlet_p95_delta_c": _delta(current.observed_temperature.get("inlet_p95_c"), previous.observed_temperature.get("inlet_p95_c")),
        "aligned_coverage_delta_pct": _delta(
            current.evidence_quality.get("coverage", {}).get("aligned_coverage_pct"),
            previous.evidence_quality.get("coverage", {}).get("aligned_coverage_pct"),
        ),
        "new_reason_codes": sorted(current_codes - previous_codes),
        "resolved_reason_codes": sorted(previous_codes - current_codes),
        "new_warnings": sorted(current_warnings - previous_warnings),
        "resolved_warnings": sorted(previous_warnings - current_warnings),
        "new_blockers": sorted(current_blockers - previous_blockers),
        "resolved_blockers": sorted(previous_blockers - current_blockers),
    }


def render_drift_markdown(drift: dict[str, Any]) -> str:
    lines = [
        "# Cabinet Envelope Drift",
        "",
        "This is a review-only comparison between two envelope outputs.",
        "",
        f"- Previous status: {drift['status_previous']}",
        f"- Current status: {drift['status_current']}",
        f"- Sustained guardrail delta kW: {drift['recommended_sustained_delta_kw']}",
        f"- Short-burst guardrail delta kW: {drift['recommended_short_burst_delta_kw']}",
        f"- Thermal slope delta C/kW: {drift['thermal_slope_delta_c_per_kw']}",
        f"- Feed imbalance delta pct: {drift['feed_imbalance_delta_pct']}",
        f"- Inlet p95 delta C: {drift['inlet_p95_delta_c']}",
        f"- Aligned coverage delta pct: {drift['aligned_coverage_delta_pct']}",
        "",
        "## New Blockers",
        "",
    ]
    lines.extend(f"- {item}" for item in drift["new_blockers"] or ["None"])
    lines.extend(["", "## New Warnings", ""])
    lines.extend(f"- {item}" for item in drift["new_warnings"] or ["None"])
    lines.extend(["", "## New Reason Codes", ""])
    lines.extend(f"- {item}" for item in drift["new_reason_codes"] or ["None"])
    lines.append("")
    return "\n".join(lines)
