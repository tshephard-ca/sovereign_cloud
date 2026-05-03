from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .guardrail import recommended_questions
from .models import AlignmentResult, CabinetEnvelope, Summary
from .normalize import isoformat_z
from .redact import Redactor


TIMESERIES_COLUMNS = [
    "timestamp",
    "cabinet_id",
    "cabinet_power_kw",
    "feed_a_kw",
    "feed_b_kw",
    "max_inlet_temp_c",
    "top_inlet_temp_c",
    "middle_inlet_temp_c",
    "bottom_inlet_temp_c",
    "power_bucket_quality",
    "temperature_bucket_quality",
    "aligned_bucket_quality",
    "notes",
]


DATA_HONESTY_CAVEATS = [
    "Seven days of telemetry may not include worst-case weather, cooling failures, maintenance modes, or workload peaks.",
    "PDU power telemetry is not a full electrical study.",
    "Inlet-temperature telemetry is not CFD.",
    "A simple thermal slope is not proof of cooling capacity.",
    "Low inlet temperature at current load does not guarantee headroom at higher load.",
    "Thermal behavior may change with blanking panels, cable management, fan curves, liquid-cooling state, containment, or neighboring cabinets.",
    "Trip thresholds must come from site policy or engineering data, not from this tool.",
    "Sales guardrails are review aids, not binding commitments.",
    "Facility engineering approval is required before using results operationally.",
]


def ensure_parent(path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def write_json(path: str | Path, data: Any) -> None:
    output = ensure_parent(path)
    if hasattr(data, "model_dump"):
        payload = data.model_dump(mode="json")
    else:
        payload = data
    with output.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
        handle.write("\n")


def write_aligned_timeseries_csv(
    path: str | Path,
    alignment: AlignmentResult,
    redact: bool = False,
    redactor: Redactor | None = None,
) -> None:
    output = ensure_parent(path)
    redactor = redactor or Redactor()
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TIMESERIES_COLUMNS)
        writer.writeheader()
        for bucket in alignment.buckets:
            cabinet_id = redactor.redact("cabinet", bucket.cabinet_id) if redact else bucket.cabinet_id
            writer.writerow(
                {
                    "timestamp": isoformat_z(bucket.timestamp),
                    "cabinet_id": cabinet_id,
                    "cabinet_power_kw": "" if bucket.cabinet_power_kw is None else bucket.cabinet_power_kw,
                    "feed_a_kw": "" if bucket.feed_power_kw.get("A") is None else bucket.feed_power_kw.get("A"),
                    "feed_b_kw": "" if bucket.feed_power_kw.get("B") is None else bucket.feed_power_kw.get("B"),
                    "max_inlet_temp_c": "" if bucket.max_inlet_temp_c is None else bucket.max_inlet_temp_c,
                    "top_inlet_temp_c": "" if bucket.top_inlet_temp_c is None else bucket.top_inlet_temp_c,
                    "middle_inlet_temp_c": "" if bucket.middle_inlet_temp_c is None else bucket.middle_inlet_temp_c,
                    "bottom_inlet_temp_c": "" if bucket.bottom_inlet_temp_c is None else bucket.bottom_inlet_temp_c,
                    "power_bucket_quality": bucket.power_bucket_quality,
                    "temperature_bucket_quality": bucket.temperature_bucket_quality,
                    "aligned_bucket_quality": bucket.aligned_bucket_quality,
                    "notes": ";".join(bucket.notes),
                }
            )


def display(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _review_lane(envelope: CabinetEnvelope) -> dict[str, Any]:
    return envelope.review_lane if isinstance(envelope.review_lane, dict) else {}


def _decision_card_lines(envelope: CabinetEnvelope) -> list[str]:
    decision = _review_lane(envelope)
    if not decision:
        return []
    actions = decision.get("next_actions") or []
    lines = [
        "## Decision Card",
        "",
        f"- Review lane: {display(decision.get('lane'))}",
        f"- Business action: {display(decision.get('business_action'))}",
        f"- Decision owner: {display(decision.get('decision_owner'))}",
        f"- Primary constraint: {display(decision.get('primary_constraint'))}",
        f"- Evidence gate: {display(decision.get('evidence_gate'))}",
        f"- Why this matters: {display(decision.get('why_this_matters'))}",
        f"- Boundary: {display(decision.get('conversation_boundary'))}",
        "",
        "## Action Queue",
        "",
    ]
    for action in actions:
        lines.append(f"- {action.get('priority', 'UNKNOWN')}: {action.get('title')} ({action.get('owner')})")
    if not actions:
        lines.append("- None")
    lines.append("")
    return lines


def render_guardrail_markdown(envelope: CabinetEnvelope) -> str:
    questions = recommended_questions(envelope.reason_codes, envelope.blockers)
    lines = [
        "# Cabinet Review Packet",
        "",
        "This is a review-only output. It is not live enforcement, not a capacity contract, and not facility approval.",
        "",
    ]
    lines.extend(_decision_card_lines(envelope))
    lines.extend(
        [
        "## Cabinet",
        "",
        f"- Cabinet ID: {envelope.cabinet_id}",
        f"- Analysis window: {envelope.window['start']} to {envelope.window['end']}",
        f"- Envelope status: {envelope.envelope_status}",
        f"- Confidence: {envelope.confidence}",
        "",
        ]
    )
    lines.extend(
        [
        "## Recommended Guardrail",
        "",
        f"- Recommended sustained kW: {display(envelope.recommended_sustained_kw)}",
        f"- Recommended short-burst kW: {display(envelope.recommended_short_burst_kw)}",
        f"- Maximum burst duration: {display(envelope.max_burst_duration_minutes)} minutes",
        f"- Limiting factor: {envelope.limiting_factor}",
        f"- Trip-risk threshold: {display(envelope.trip_risk_threshold_kw)} kW",
        f"- Thermal-risk threshold: {display(envelope.thermal_risk_threshold_kw)} kW",
        "",
        "## Guardrail Language",
        "",
        envelope.sales_ops_guardrail.text,
        "",
        ]
    )
    lines.extend(
        [
        "## Observed Evidence",
        "",
        f"- Observed power p95/p99: {display(envelope.observed_power.get('p95_kw'))} / {display(envelope.observed_power.get('p99_kw'))} kW",
        f"- Observed sustained p95: {display(envelope.observed_power.get('sustained_p95_kw'))} kW",
        f"- Observed short-burst p99: {display(envelope.observed_power.get('short_burst_p99_kw'))} kW",
        f"- Observed inlet p95/p99/max: {display(envelope.observed_temperature.get('inlet_p95_c'))} / {display(envelope.observed_temperature.get('inlet_p99_c'))} / {display(envelope.observed_temperature.get('inlet_max_c'))} deg C",
        "",
        "## Reason Codes",
        "",
        ]
    )
    lines.extend(f"- {code}" for code in envelope.reason_codes or ["None"])
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {code}" for code in envelope.warnings or ["None"])
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- {code}" for code in envelope.blockers or ["None"])
    lines.extend(["", "## Recommended Human Questions", ""])
    lines.extend(f"- {question}" for question in questions)
    lines.extend(["", "## Data Honesty Caveats", ""])
    lines.extend(f"- {caveat}" for caveat in DATA_HONESTY_CAVEATS)
    lines.append("")
    return "\n".join(lines)


def write_guardrail_markdown(path: str | Path, envelope: CabinetEnvelope) -> None:
    output = ensure_parent(path)
    output.write_text(render_guardrail_markdown(envelope), encoding="utf-8")


def render_explanation_markdown(envelope: CabinetEnvelope) -> str:
    lines = [
        "# Envelope Explanation",
        "",
        "This explanation describes how the review-only cabinet envelope was calculated from normalized input files.",
        "",
        f"- Cabinet ID: {envelope.cabinet_id}",
        f"- Status: {envelope.envelope_status}",
        f"- Confidence: {envelope.confidence}",
        f"- Review lane: {display(_review_lane(envelope).get('lane'))}",
        f"- Business action: {display(_review_lane(envelope).get('business_action'))}",
        f"- Recommended sustained kW: {display(envelope.recommended_sustained_kw)}",
        f"- Recommended short-burst kW: {display(envelope.recommended_short_burst_kw)}",
        f"- Limiting factor: {envelope.limiting_factor}",
        "",
        "## Electrical Basis",
        "",
        f"- Sustained limit from profile: {display(envelope.electrical.get('sustained_limit_kw'))} kW",
        f"- Burst limit from profile: {display(envelope.electrical.get('burst_limit_kw'))} kW",
        f"- Power guardband: {display(envelope.electrical.get('power_guardband_kw'))} kW",
        f"- Trip-risk threshold from profile: {display(envelope.trip_risk_threshold_kw)} kW",
        "",
        "## Thermal Basis",
        "",
        f"- Thermal model status: {envelope.thermal.get('thermal_model_status')}",
        f"- Thermal slope: {display(envelope.thermal.get('slope_c_per_kw'))} deg C/kW",
        f"- Thermal model r2: {display(envelope.thermal.get('r_squared'))}",
        f"- Best observed thermal lag: {display(envelope.thermal.get('best_lag_minutes'))} minutes",
        f"- Best lag r2: {display(envelope.thermal.get('best_lag_r_squared'))}",
        f"- Predicted warning power: {display(envelope.thermal.get('predicted_warning_power_kw'))} kW",
        "",
        "## Caveats",
        "",
    ]
    lines.extend(f"- {caveat}" for caveat in DATA_HONESTY_CAVEATS)
    lines.append("")
    return "\n".join(lines)


def write_explanation_markdown(path: str | Path, envelope: CabinetEnvelope) -> None:
    output = ensure_parent(path)
    output.write_text(render_explanation_markdown(envelope), encoding="utf-8")


def render_explanation_json(envelope: CabinetEnvelope) -> dict[str, Any]:
    electrical_candidate = envelope.electrical.get("sustained_guardrail_kw")
    thermal_candidate = envelope.thermal.get("thermal_guardrail_sustained_kw")
    burst_electrical_candidate = envelope.electrical.get("burst_guardrail_kw")
    burst_thermal_candidate = envelope.thermal.get("thermal_guardrail_burst_kw")
    return {
        "schema_version": "cabinet-burst-envelope.explanation.v1",
        "tool_version": envelope.tool_version,
        "cabinet_id": envelope.cabinet_id,
        "generated_at": isoformat_z(envelope.generated_at),
        "window": envelope.window,
        "status": envelope.envelope_status,
        "confidence": envelope.confidence,
        "limiting_factor": envelope.limiting_factor,
        "review_lane": envelope.review_lane,
        "calculation_trace": {
            "sustained_candidates_kw": {
                "electrical": electrical_candidate,
                "thermal": thermal_candidate,
                "selected": envelope.recommended_sustained_kw,
                "rounding": "floor_to_one_decimal",
            },
            "short_burst_candidates_kw": {
                "electrical": burst_electrical_candidate,
                "thermal": burst_thermal_candidate,
                "trip_risk_cap": envelope.trip_risk_threshold_kw,
                "selected": envelope.recommended_short_burst_kw,
                "rounding": "floor_to_one_decimal",
            },
            "electrical_basis": {
                "sustained_limit_kw": envelope.electrical.get("sustained_limit_kw"),
                "burst_limit_kw": envelope.electrical.get("burst_limit_kw"),
                "power_guardband_kw": envelope.electrical.get("power_guardband_kw"),
                "trip_risk": envelope.electrical.get("trip_risk"),
                "feed_imbalance_pct": envelope.electrical.get("feed_imbalance_pct"),
            },
            "thermal_basis": {
                "thermal_model_status": envelope.thermal.get("thermal_model_status"),
                "slope_c_per_kw": envelope.thermal.get("slope_c_per_kw"),
                "r_squared": envelope.thermal.get("r_squared"),
                "best_lag_minutes": envelope.thermal.get("best_lag_minutes"),
                "best_lag_r_squared": envelope.thermal.get("best_lag_r_squared"),
                "predicted_warning_power_kw": envelope.thermal.get("predicted_warning_power_kw"),
                "predicted_critical_power_kw": envelope.thermal.get("predicted_critical_power_kw"),
                "thermal_risk": envelope.thermal.get("thermal_risk"),
            },
            "observed_power": envelope.observed_power,
            "observed_temperature": envelope.observed_temperature,
            "evidence_quality": envelope.evidence_quality,
        },
        "reason_codes": envelope.reason_codes,
        "decision_trace": (envelope.review_lane or {}).get("decision_trace") if isinstance(envelope.review_lane, dict) else None,
        "action_queue": (envelope.review_lane or {}).get("next_actions", []) if isinstance(envelope.review_lane, dict) else [],
        "warnings": envelope.warnings,
        "blockers": envelope.blockers,
        "missing_data": envelope.missing_data,
        "assumptions": envelope.assumptions,
        "data_honesty_caveats": DATA_HONESTY_CAVEATS,
    }


def write_explanation_json(path: str | Path, envelope: CabinetEnvelope) -> None:
    write_json(path, render_explanation_json(envelope))


def _redact_nested_ids(value: Any, redactor: Redactor) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key == "cabinet_id":
                out[key] = redactor.redact("cabinet", item)
            elif key == "display_name":
                out[key] = redactor.redact("display_name", item)
            else:
                out[key] = _redact_nested_ids(item, redactor)
        return out
    if isinstance(value, list):
        return [_redact_nested_ids(item, redactor) for item in value]
    return value


def redact_envelope(envelope: CabinetEnvelope, redactor: Redactor | None = None) -> CabinetEnvelope:
    redactor = redactor or Redactor()
    payload = envelope.model_dump(mode="python")
    payload = _redact_nested_ids(payload, redactor)
    return CabinetEnvelope.model_validate(payload)


def redact_summary(summary: Summary, redactor: Redactor | None = None) -> Summary:
    redactor = redactor or Redactor()
    payload = summary.model_dump(mode="python")
    payload = _redact_nested_ids(payload, redactor)
    return Summary.model_validate(payload)
