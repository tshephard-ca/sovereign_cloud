from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .models import CompatibilitySummary, Mismatch, ProbePlan, ProbeResults, UsageProfile
from .usage_profile import confidence_from_profile


NEEDS_COLUMNS = [
    "operation_family",
    "event_name",
    "observed_count",
    "evidence_source",
    "required_for_probe",
    "sample_key_shape",
    "observed_request_features",
    "observed_response_features",
    "risk_flags",
    "notes",
]

MISMATCH_COLUMNS = [
    "severity",
    "probe_id",
    "operation_family",
    "operation",
    "evidence_source",
    "expected",
    "actual",
    "mismatch_code",
    "reason_text",
    "business_impact",
    "suggested_human_question",
]


def write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_text(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def write_needs_csv(path: str | Path, profile: UsageProfile) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    shape = profile.key_shapes[0].prefix_template if profile.key_shapes else ""
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=NEEDS_COLUMNS)
        writer.writeheader()
        for family_name, family in sorted(profile.operation_families.items()):
            for event_name, count in sorted(family.event_names.items()):
                writer.writerow(
                    {
                        "operation_family": family_name,
                        "event_name": event_name,
                        "observed_count": count,
                        "evidence_source": "CLOUDTRAIL",
                        "required_for_probe": "true" if family_name != "unknown" else "false",
                        "sample_key_shape": shape,
                        "observed_request_features": ";".join(family.observed_features),
                        "observed_response_features": "",
                        "risk_flags": ";".join(profile.risk_flags),
                        "notes": "",
                    }
                )
        for feature in profile.request_hint_features:
            writer.writerow(
                {
                    "operation_family": _feature_family(feature),
                    "event_name": "",
                    "observed_count": 0,
                    "evidence_source": "REQUEST_HINTS",
                    "required_for_probe": "false",
                    "sample_key_shape": shape,
                    "observed_request_features": feature,
                    "observed_response_features": "",
                    "risk_flags": "",
                    "notes": "user-supplied request hint",
                }
            )
        for feature in profile.bucket_config_features:
            writer.writerow(
                {
                    "operation_family": _feature_family(feature),
                    "event_name": "",
                    "observed_count": 0,
                    "evidence_source": "BUCKET_CONFIG",
                    "required_for_probe": "false",
                    "sample_key_shape": shape,
                    "observed_request_features": feature,
                    "observed_response_features": "",
                    "risk_flags": "LIFECYCLE_STATIC_ONLY" if feature == "LIFECYCLE" else "",
                    "notes": "user-supplied bucket context",
                }
            )


def write_mismatches_csv(path: str | Path, results: ProbeResults) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MISMATCH_COLUMNS)
        writer.writeheader()
        for mismatch in collect_mismatches(results):
            writer.writerow(mismatch.model_dump(mode="json"))


def collect_mismatches(results: ProbeResults) -> list[Mismatch]:
    mismatches: list[Mismatch] = []
    for result in results.results:
        mismatches.extend(result.mismatches)
    return mismatches


def build_summary(profile: UsageProfile, results: ProbeResults | None = None, plan: ProbePlan | None = None) -> CompatibilitySummary:
    results = results or ProbeResults(
        run_id="not-run",
        endpoint_url_redacted="not-run",
        target_bucket_redacted="not-run",
        scratch_prefix="not-run",
        started_at="not-run",
        finished_at="not-run",
        cleanup={"attempted": False, "succeeded": False, "cleanup_manifest": None},
    )
    mismatches = collect_mismatches(results)
    mismatch_counts = {
        "BLOCKER": sum(1 for mismatch in mismatches if mismatch.severity == "BLOCKER"),
        "REVIEW": sum(1 for mismatch in mismatches if mismatch.severity == "REVIEW"),
        "INFO": sum(1 for mismatch in mismatches if mismatch.severity == "INFO"),
    }
    required_ids = {probe.id for probe in plan.probes if probe.required} if plan else set()
    required = [result for result in results.results if result.probe_id in required_ids] if required_ids else [result for result in results.results if _is_required_status(result.probe_id)]
    required_passed = sum(1 for result in required if result.status == "PASS")
    required_failed = sum(1 for result in required if result.status == "FAIL")
    required_review = sum(1 for result in required if result.status == "REVIEW")
    required_skipped = sum(1 for result in required if result.status == "SKIP")
    optional = max(len(results.results) - len(required), 0)
    target_status = _compatibility_status(mismatch_counts, required_skipped, results)
    confidence = _summary_confidence(profile, results, required_skipped)
    evidence_status = _evidence_coverage_status(profile, confidence)
    cutover_recommendation = _cutover_recommendation(target_status, confidence, bool(results.results))
    top_risks = [
        {"code": mismatch.mismatch_code, "severity": mismatch.severity, "business_impact": mismatch.business_impact}
        for mismatch in sorted(mismatches, key=lambda m: _severity_order(m.severity))[:5]
    ]
    questions = []
    for mismatch in mismatches:
        if mismatch.severity in {"BLOCKER", "REVIEW"} and mismatch.suggested_human_question not in questions:
            questions.append(mismatch.suggested_human_question)
    if not questions and any(code in profile.observed_features for code in ("CORS", "OBJECT_LOCK", "PRESIGNED_OBSERVED", "VERSIONING")):
        questions.extend(
            [
                "Which CORS origins and request headers must be supported?",
                "Are presigned URLs used by external users?",
                "Does application logic depend on version IDs?",
            ]
        )
    return CompatibilitySummary(
        compatibility_status=target_status,
        evidence_coverage_status=evidence_status,
        target_semantic_status=target_status,
        cutover_recommendation=cutover_recommendation,
        confidence=confidence,
        source_profile={
            "event_count": profile.event_count,
            "processed_event_count": profile.processed_event_count,
            "operation_families_observed": len([f for f in profile.operation_families.values() if f.count > 0]),
            "time_range": profile.time_range.model_dump(mode="json"),
        },
        coverage={
            "required_probe_count": len(required),
            "required_probes_passed": required_passed,
            "required_probes_failed": required_failed,
            "required_probes_review": required_review,
            "required_probes_skipped": required_skipped,
            "optional_probe_count": optional,
        },
        mismatch_counts=mismatch_counts,
        top_risks=top_risks,
        recommended_next_questions=questions[:10],
        warnings=sorted(set(profile.warnings) | set(results.warnings)),
    )


def summary_markdown(summary: CompatibilitySummary) -> str:
    lines = [
        "# Compatibility Preflight Summary",
        "",
        f"Cutover recommendation: **{summary.cutover_recommendation}**",
        f"Target semantic status: **{summary.target_semantic_status}**",
        f"Evidence coverage status: **{summary.evidence_coverage_status}**",
        f"Confidence: **{summary.confidence}**",
        "",
        "## Coverage",
        "",
        f"- Required probes passed: {summary.coverage['required_probes_passed']}",
        f"- Required probes failed: {summary.coverage['required_probes_failed']}",
        f"- Required probes needing review: {summary.coverage.get('required_probes_review', 0)}",
        f"- Required probes skipped: {summary.coverage['required_probes_skipped']}",
        f"- Optional probes: {summary.coverage['optional_probe_count']}",
        "",
        "## Top Risks",
        "",
    ]
    if summary.top_risks:
        for risk in summary.top_risks:
            lines.append(f"- {risk['severity']} {risk['code']}: {risk['business_impact']}")
    else:
        lines.append("- No blocker or review risks were reported by the synthetic probe results.")
    lines.extend(["", "## Recommended Next Questions", ""])
    if summary.recommended_next_questions:
        for question in summary.recommended_next_questions:
            lines.append(f"- {question}")
    else:
        lines.append("- Confirm that the observed CloudTrail-style evidence covers the application paths that matter.")
    lines.extend(["", "## Caveat", "", "A successful probe plan does not prove full migration readiness. Synthetic probes are not production traffic."])
    return "\n".join(lines) + "\n"


def _compatibility_status(mismatch_counts: dict[str, int], required_skipped: int, results: ProbeResults) -> str:
    if not results.results:
        return "REVIEW"
    if mismatch_counts.get("BLOCKER", 0) > 0 or results.probes_failed > 0:
        return "FAIL"
    if required_skipped > 0 or mismatch_counts.get("REVIEW", 0) > 0:
        return "REVIEW"
    return "PASS"


def _summary_confidence(profile: UsageProfile, results: ProbeResults, required_skipped: int) -> str:
    base = confidence_from_profile(profile, target_probe_ran=bool(results.results))
    if required_skipped > 0 or any(result.status == "SKIP" for result in results.results):
        return "LOW" if base == "MEDIUM" else "MEDIUM"
    return base


def _evidence_coverage_status(profile: UsageProfile, confidence: str) -> str:
    if profile.processed_event_count == 0:
        return "FAIL"
    if confidence == "LOW" or profile.evidence_quality.truncated_or_missing_fields:
        return "REVIEW"
    return "PASS"


def _cutover_recommendation(target_status: str, confidence: str, target_probe_ran: bool) -> str:
    if not target_probe_ran:
        return "REVIEW"
    if target_status == "FAIL":
        return "BLOCK"
    if target_status == "REVIEW" or confidence == "LOW":
        return "REVIEW"
    return "PROCEED_WITH_CAVEATS"


def _is_required_status(probe_id: str) -> bool:
    return not probe_id.startswith("lifecycle_static")


def _severity_order(severity: str) -> int:
    return {"BLOCKER": 0, "REVIEW": 1, "INFO": 2}.get(severity, 3)


def _feature_family(feature: str) -> str:
    return {
        "PRESIGNED_OBSERVED": "presigned",
        "CORS": "cors",
        "OBJECT_LOCK": "object_lock",
        "VERSIONING": "versioning",
        "LIFECYCLE": "lifecycle",
        "OBJECT_TAGGING": "tagging",
        "ACL": "acl",
    }.get(feature, "unknown")
