from __future__ import annotations

from .guardrail import recommended_questions
from .models import AlignmentResult, CabinetEnvelope


def _check_item(name: str, passed: bool, detail: str, remediation: str | None = None) -> dict:
    return {
        "name": name,
        "passed": passed,
        "detail": detail,
        "remediation": remediation,
    }


def build_preflight_checklist(envelope: CabinetEnvelope, alignment: AlignmentResult) -> list[dict]:
    coverage = alignment.coverage
    reason_codes = set(envelope.reason_codes)
    warnings = set(envelope.warnings)
    blockers = set(envelope.blockers)
    missing_data = set(envelope.missing_data)
    return [
        _check_item(
            "power_data_present",
            "POWER_DATA_MISSING" not in missing_data and coverage.power_buckets > 0,
            f"{coverage.power_buckets}/{coverage.expected_buckets} buckets contain power readings.",
            "Provide normalized PDU active kW readings for the selected cabinet.",
        ),
        _check_item(
            "temperature_data_present",
            "TEMPERATURE_DATA_MISSING" not in missing_data and coverage.temperature_buckets > 0,
            f"{coverage.temperature_buckets}/{coverage.expected_buckets} buckets contain valid inlet temperature readings.",
            "Provide normalized inlet-temperature readings for the selected cabinet.",
        ),
        _check_item(
            "aligned_coverage_sufficient",
            "ALIGNED_COVERAGE_TOO_LOW" not in blockers and "ALIGNED_COVERAGE_LOW" not in warnings,
            f"Aligned coverage is {coverage.aligned_coverage_pct}%.",
            "Collect a fuller overlapping window of power and inlet-temperature telemetry.",
        ),
        _check_item(
            "cabinet_profile_valid",
            "PROFILE_INVALID" not in blockers and "PROFILE_INVALID" not in missing_data,
            "Cabinet profile limits are internally consistent." if "PROFILE_INVALID" not in missing_data else "Cabinet profile contains contradictory limits.",
            "Correct contradictory sustained, burst, trip, or thermal thresholds in the cabinet profile.",
        ),
        _check_item(
            "electrical_limit_present",
            "ELECTRICAL_LIMIT_MISSING" not in reason_codes,
            "Site-supplied sustained electrical limit is present." if "ELECTRICAL_LIMIT_MISSING" not in reason_codes else "Sustained electrical limit is missing.",
            "Add the site-approved sustained kW limit to the cabinet profile.",
        ),
        _check_item(
            "trip_threshold_present",
            "TRIP_THRESHOLD_NOT_SUPPLIED" not in warnings,
            "Trip-risk threshold is present." if "TRIP_THRESHOLD_NOT_SUPPLIED" not in warnings else "Trip-risk threshold is missing.",
            "Add the site-approved trip-risk threshold to the cabinet profile.",
        ),
        _check_item(
            "thermal_limits_present",
            "THERMAL_LIMIT_MISSING" not in reason_codes,
            "Thermal warning and critical thresholds are present." if "THERMAL_LIMIT_MISSING" not in reason_codes else "Thermal warning or critical threshold is missing.",
            "Add inlet warning and critical thresholds from site policy.",
        ),
        _check_item(
            "valid_inlet_sensors_present",
            "NO_VALID_INLET_SENSOR" not in missing_data,
            "At least one valid inlet/front sensor is present." if "NO_VALID_INLET_SENSOR" not in missing_data else "No valid inlet/front sensor is present.",
            "Map or repair front inlet temperature sensors before using the envelope.",
        ),
        _check_item(
            "top_middle_bottom_sensors_present",
            "TOP_MIDDLE_BOTTOM_SENSORS_PRESENT" in reason_codes,
            "Top, middle, and bottom inlet sensors are present." if "TOP_MIDDLE_BOTTOM_SENSORS_PRESENT" in reason_codes else "One or more top/middle/bottom inlet positions are missing.",
            "Add or repair missing top, middle, or bottom inlet sensing.",
        ),
        _check_item(
            "power_readings_not_all_zero",
            "ALL_ZERO_POWER_READINGS" not in warnings,
            "Power readings are not all zero." if "ALL_ZERO_POWER_READINGS" not in warnings else "All selected power readings are zero.",
            "Confirm the normalized power export contains active kW readings and not missing telemetry encoded as zero.",
        ),
        _check_item(
            "no_blockers",
            not envelope.blockers,
            "No blockers are present." if not envelope.blockers else f"{len(envelope.blockers)} blocker(s) are present.",
            "Resolve blockers before considering additional bursty load.",
        ),
    ]


def build_doctor_report(envelope: CabinetEnvelope, alignment: AlignmentResult) -> dict:
    ready = envelope.envelope_status not in {"INSUFFICIENT_DATA", "DO_NOT_EXPAND"}
    checklist = build_preflight_checklist(envelope, alignment)
    return {
        "schema_version": "cabinet-burst-envelope.doctor.v1",
        "cabinet_id": envelope.cabinet_id,
        "ready_for_estimate": ready,
        "preflight_passed": all(item["passed"] for item in checklist),
        "envelope_status": envelope.envelope_status,
        "confidence": envelope.confidence,
        "evidence_quality": envelope.evidence_quality,
        "coverage": alignment.coverage.model_dump(mode="json"),
        "preflight_checklist": checklist,
        "missing_data": envelope.missing_data,
        "warnings": envelope.warnings,
        "blockers": envelope.blockers,
        "reason_codes": envelope.reason_codes,
        "recommended_next_questions": recommended_questions(envelope.reason_codes, envelope.blockers),
    }


def render_doctor_markdown(report: dict) -> str:
    lines = [
        "# Cabinet Input Doctor",
        "",
        "This is a local review-only input diagnostic. It does not approve capacity or change operational settings.",
        "",
        f"- Cabinet ID: {report['cabinet_id']}",
        f"- Ready for estimate discussion: {report['ready_for_estimate']}",
        f"- Preflight passed: {report['preflight_passed']}",
        f"- Envelope status: {report['envelope_status']}",
        f"- Confidence: {report['confidence']}",
        f"- Evidence quality: {report['evidence_quality'].get('score')} ({report['evidence_quality'].get('band')})",
        "",
        "## Preflight Checklist",
        "",
    ]
    for item in report["preflight_checklist"]:
        status = "PASS" if item["passed"] else "FAIL"
        lines.append(f"- {status}: {item['name']} - {item['detail']}")
        if not item["passed"] and item.get("remediation"):
            lines.append(f"  Remediation: {item['remediation']}")
    lines.extend([
        "",
        "## Missing Data",
        "",
    ])
    lines.extend(f"- {item}" for item in report["missing_data"] or ["None"])
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {item}" for item in report["warnings"] or ["None"])
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- {item}" for item in report["blockers"] or ["None"])
    lines.extend(["", "## Recommended Questions", ""])
    lines.extend(f"- {item}" for item in report["recommended_next_questions"])
    lines.append("")
    return "\n".join(lines)
