from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from .capabilities import capability_for_family, family_for_feature, family_for_mismatch_code
from .models import (
    CapabilityFinding,
    CompatibilitySummary,
    CutoverDecisionBrief,
    EvidenceLedgerItem,
    ProbePlan,
    ProbeResults,
    QuestionnaireItem,
    RemediationItem,
    SafetyGateSummary,
    UsageProfile,
)
from .questionnaire import generate_questionnaire
from .report import collect_mismatches


CAPABILITY_LEDGER_COLUMNS = [
    "capability",
    "business_flow",
    "owner_role",
    "why_it_matters",
    "observed_evidence",
    "required_by_workflow",
    "probe_ids",
    "probe_status",
    "severity",
    "mismatch_codes",
    "next_action",
]

REMEDIATION_COLUMNS = [
    "severity",
    "capability",
    "business_flow",
    "owner_role",
    "probe_id",
    "mismatch_code",
    "business_impact",
    "next_action",
    "question",
]


def load_business_context(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def build_capability_ledger(
    profile: UsageProfile,
    plan: ProbePlan,
    results: ProbeResults | None = None,
    business_context: dict[str, Any] | None = None,
) -> list[CapabilityFinding]:
    business_context = business_context or {}
    results = results or _empty_results(plan)
    mismatches = collect_mismatches(results)
    observed_by_family: dict[str, set[str]] = defaultdict(set)
    for family, data in profile.operation_families.items():
        if data.count:
            observed_by_family[family].add(f"CLOUDTRAIL:{data.count}")
        for feature in data.observed_features:
            observed_by_family[family_for_feature(feature)].add(f"CLOUDTRAIL_FEATURE:{feature}")
    for feature in profile.request_hint_features:
        observed_by_family[family_for_feature(feature)].add(f"REQUEST_HINT:{feature}")
    for feature in profile.bucket_config_features:
        observed_by_family[family_for_feature(feature)].add(f"BUCKET_CONFIG:{feature}")

    probes_by_family: dict[str, list[str]] = defaultdict(list)
    required_by_family: dict[str, bool] = defaultdict(bool)
    for probe in plan.probes:
        probes_by_family[probe.family].append(probe.id)
        required_by_family[probe.family] = required_by_family[probe.family] or probe.required

    status_by_probe = {result.probe_id: result.status for result in results.results}
    severity_by_family: dict[str, str] = defaultdict(lambda: "INFO")
    codes_by_family: dict[str, set[str]] = defaultdict(set)
    for mismatch in mismatches:
        family = family_for_mismatch_code(mismatch.mismatch_code, mismatch.operation_family)
        codes_by_family[family].add(mismatch.mismatch_code)
        severity_by_family[family] = _max_severity(severity_by_family[family], mismatch.severity)

    families = sorted(set(observed_by_family) | set(probes_by_family) | set(codes_by_family))
    findings: list[CapabilityFinding] = []
    for family in families:
        definition = capability_for_family(family)
        probe_ids = probes_by_family.get(family, [])
        probe_status = _aggregate_status([status_by_probe.get(probe_id, "NOT_RUN") for probe_id in probe_ids])
        findings.append(
            CapabilityFinding(
                capability=definition.capability,
                business_flow=_business_flow(definition.business_flow, business_context),
                owner_role=definition.owner_role,
                why_it_matters=definition.why_it_matters,
                observed_evidence=sorted(observed_by_family.get(family, [])),
                required_by_workflow=required_by_family.get(family, False) or bool(codes_by_family.get(family)),
                probe_ids=probe_ids,
                probe_status=probe_status,
                severity=severity_by_family[family],
                mismatch_codes=sorted(codes_by_family.get(family, [])),
                next_action=definition.next_action,
            )
        )
    return findings


def build_cutover_brief(
    profile: UsageProfile,
    plan: ProbePlan,
    results: ProbeResults | None,
    summary: CompatibilitySummary,
    *,
    business_context: dict[str, Any] | None = None,
) -> CutoverDecisionBrief:
    business_context = business_context or {}
    effective_results = results or _empty_results(plan)
    mismatches = collect_mismatches(effective_results)
    capability_ledger = build_capability_ledger(profile, plan, effective_results, business_context)
    remediation_items = [_remediation_item(mismatch, business_context) for mismatch in mismatches if mismatch.severity in {"BLOCKER", "REVIEW"}]
    blockers = [item for item in remediation_items if item.severity == "BLOCKER"]
    review_items = [item for item in remediation_items if item.severity == "REVIEW"]
    questionnaire = generate_questionnaire(profile, mismatches)
    recommendation = summary.cutover_recommendation
    if results is None or not results.results:
        recommendation = "REVIEW"
    affected = _affected_business_flows(remediation_items, capability_ledger)
    return CutoverDecisionBrief(
        cutover_recommendation=recommendation,
        evidence_coverage_status=summary.evidence_coverage_status,
        target_semantic_status=summary.target_semantic_status,
        confidence=summary.confidence,
        business_throughline="Use observed S3-style behavior to prove the target supports the application semantics that matter before cutover.",
        source_bucket_redacted=profile.source_bucket,
        result_source=effective_results.result_source,
        first_read={
            "blocker_count": len(blockers),
            "review_count": len(review_items),
            "required_probe_count": summary.coverage.get("required_probe_count", 0),
            "required_probes_failed": summary.coverage.get("required_probes_failed", 0),
            "required_probes_skipped": summary.coverage.get("required_probes_skipped", 0),
            "capability_count": len(capability_ledger),
            "top_business_flows": [item["business_flow"] for item in affected[:5]],
        },
        affected_business_flows=affected,
        blockers=blockers,
        review_items=review_items,
        owner_questions=questionnaire.questions,
        capability_ledger=capability_ledger,
        evidence_ledger=_evidence_ledger(profile, plan, effective_results, business_context),
        safety_gates=_safety_gates(plan, effective_results),
        untested_assumptions=_untested_assumptions(profile, plan, effective_results),
        caveats=[
            "Synthetic probes are not production traffic.",
            "This preflight does not migrate data, benchmark performance, or certify full application cutover readiness.",
        ],
    )


def write_cutover_brief_json(path: str | Path, brief: CutoverDecisionBrief) -> None:
    _write_text(path, json.dumps(brief.model_dump(mode="json"), indent=2, sort_keys=True) + "\n")


def write_cutover_brief_markdown(path: str | Path, brief: CutoverDecisionBrief) -> None:
    _write_text(path, cutover_brief_markdown(brief))


def write_capability_ledger_csv(path: str | Path, findings: list[CapabilityFinding]) -> None:
    _write_csv(path, CAPABILITY_LEDGER_COLUMNS, [finding.model_dump(mode="json") for finding in findings])


def write_remediation_queue_csv(path: str | Path, items: list[RemediationItem]) -> None:
    _write_csv(path, REMEDIATION_COLUMNS, [item.model_dump(mode="json") for item in items])


def write_owner_questions_yaml(path: str | Path, questions: list[QuestionnaireItem]) -> None:
    payload = {"schema_version": 1, "questions": [question.model_dump(mode="json") for question in questions]}
    _write_text(path, yaml.safe_dump(payload, sort_keys=False))


def cutover_brief_markdown(brief: CutoverDecisionBrief) -> str:
    lines = [
        "# S3 Compatibility Cutover Brief",
        "",
        f"- Cutover recommendation: **{brief.cutover_recommendation}**",
        f"- Target semantic status: **{brief.target_semantic_status}**",
        f"- Evidence coverage status: **{brief.evidence_coverage_status}**",
        f"- Confidence: **{brief.confidence}**",
        f"- Result source: `{brief.result_source}`",
        "",
        "## Business Throughline",
        "",
        brief.business_throughline,
        "",
        "## First Read",
        "",
    ]
    for key, value in brief.first_read.items():
        label = key.replace("_", " ")
        if isinstance(value, list):
            lines.append(f"- {label}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"- {label}: {value}")
    lines.extend(["", "## Affected Business Flows", ""])
    if brief.affected_business_flows:
        for flow in brief.affected_business_flows:
            lines.append(f"- {flow['business_flow']}: {flow['blocker_count']} blocker(s), {flow['review_count']} review item(s), owner `{flow['owner_role']}`")
    else:
        lines.append("- No blocker or review flows were identified.")
    lines.extend(["", "## Blockers", ""])
    lines.extend(_remediation_lines(brief.blockers, empty="No blocker mismatches were reported."))
    lines.extend(["", "## Review Items", ""])
    lines.extend(_remediation_lines(brief.review_items, empty="No review mismatches were reported."))
    lines.extend(["", "## Owner Questions", ""])
    if brief.owner_questions:
        by_owner: dict[str, list[QuestionnaireItem]] = defaultdict(list)
        for question in brief.owner_questions:
            by_owner[question.owner_role].append(question)
        for owner in sorted(by_owner):
            lines.append(f"### {owner}")
            lines.append("")
            for question in by_owner[owner]:
                flag = "blocks cutover" if question.blocks_cutover_if_unanswered else "answer required" if question.answer_required else "optional"
                lines.append(f"- [{question.severity}] {question.question} ({flag})")
            lines.append("")
    else:
        lines.append("- No owner questions were generated.")
    lines.extend(["", "## Safety Gates", ""])
    safety = brief.safety_gates
    lines.extend(
        [
            f"- Scratch prefix: `{safety.scratch_prefix}`",
            f"- Synthetic objects only: `{safety.synthetic_objects_only}`",
            f"- Source bucket accessed: `{safety.source_bucket_accessed}`",
            f"- Unsafe probe count: `{safety.unsafe_probe_count}`",
            f"- Skipped probe count: `{safety.skipped_probe_count}`",
        ]
    )
    lines.extend(["", "## Untested Assumptions", ""])
    if brief.untested_assumptions:
        lines.extend(f"- {item}" for item in brief.untested_assumptions)
    else:
        lines.append("- No untested assumptions were identified by this package.")
    lines.extend(["", "## Caveats", ""])
    lines.extend(f"- {item}" for item in brief.caveats)
    return "\n".join(lines).rstrip() + "\n"


def _remediation_item(mismatch: Any, business_context: dict[str, Any]) -> RemediationItem:
    family = family_for_mismatch_code(mismatch.mismatch_code, mismatch.operation_family)
    definition = capability_for_family(family)
    return RemediationItem(
        severity=mismatch.severity,
        capability=definition.capability,
        business_flow=_business_flow(definition.business_flow, business_context),
        owner_role=definition.owner_role,
        probe_id=mismatch.probe_id,
        mismatch_code=mismatch.mismatch_code,
        business_impact=mismatch.business_impact,
        next_action=definition.next_action,
        question=mismatch.suggested_human_question,
    )


def _remediation_lines(items: list[RemediationItem], *, empty: str) -> list[str]:
    if not items:
        return [f"- {empty}"]
    lines: list[str] = []
    for item in items:
        lines.extend(
            [
                f"### {item.mismatch_code}",
                "",
                f"- Capability: {item.capability}",
                f"- Business flow: {item.business_flow}",
                f"- Owner: `{item.owner_role}`",
                f"- Probe: `{item.probe_id}`",
                f"- Impact: {item.business_impact}",
                f"- Next action: {item.next_action}",
                f"- Question: {item.question}",
                "",
            ]
        )
    return lines


def _affected_business_flows(remediation_items: list[RemediationItem], capability_ledger: list[CapabilityFinding]) -> list[dict[str, Any]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    owners: dict[str, str] = {}
    for item in remediation_items:
        counts[item.business_flow][item.severity] += 1
        owners.setdefault(item.business_flow, item.owner_role)
    for finding in capability_ledger:
        owners.setdefault(finding.business_flow, finding.owner_role)
    output = []
    for flow, counter in counts.items():
        output.append(
            {
                "business_flow": flow,
                "owner_role": owners.get(flow, "storage architect"),
                "blocker_count": counter.get("BLOCKER", 0),
                "review_count": counter.get("REVIEW", 0),
            }
        )
    return sorted(output, key=lambda item: (-item["blocker_count"], -item["review_count"], item["business_flow"]))


def _evidence_ledger(profile: UsageProfile, plan: ProbePlan, results: ProbeResults, business_context: dict[str, Any]) -> list[EvidenceLedgerItem]:
    items = [
        EvidenceLedgerItem(evidence_type="usage_profile", item=f"{profile.processed_event_count} processed events", source="CloudTrail-style events"),
        EvidenceLedgerItem(evidence_type="probe_plan", item=f"{len(plan.probes)} probes", source="generated probe plan"),
        EvidenceLedgerItem(evidence_type="probe_results", item=f"{len(results.results)} results", source=results.result_source),
    ]
    for feature in profile.request_hint_features:
        items.append(EvidenceLedgerItem(evidence_type="request_hint", item=feature, source="request-hints.yml"))
    for feature in profile.bucket_config_features:
        items.append(EvidenceLedgerItem(evidence_type="bucket_config", item=feature, source="source-bucket-config.yml"))
    for flow in business_context.get("critical_flows", [])[:10]:
        items.append(EvidenceLedgerItem(evidence_type="business_context", item=str(flow), source="business-context.yml"))
    return items


def _safety_gates(plan: ProbePlan, results: ProbeResults) -> SafetyGateSummary:
    return SafetyGateSummary(
        scratch_prefix=results.scratch_prefix or plan.scratch_prefix,
        synthetic_objects_only=bool(plan.safety.get("uses_synthetic_objects_only", True)),
        unsafe_probe_count=sum(1 for probe in plan.probes if probe.requires_allow_deletes or probe.requires_allow_acl_tests or probe.requires_allow_multipart or probe.requires_allow_object_lock_tests),
        skipped_probe_count=results.probes_skipped,
        warnings=sorted(set(plan.warnings) | set(results.warnings)),
    )


def _untested_assumptions(profile: UsageProfile, plan: ProbePlan, results: ProbeResults) -> list[str]:
    assumptions: list[str] = []
    if results.result_source.startswith("simulated"):
        assumptions.append("Probe results are simulated and validate reporting coverage, not a live endpoint.")
    if "LIFECYCLE_STATIC_ONLY" in profile.warnings or any("LIFECYCLE_STATIC_ONLY" in probe.warnings for probe in plan.probes):
        assumptions.append("Lifecycle behavior is static-review only and must be validated outside the short replay.")
    if results.probes_skipped:
        assumptions.append("Some probes were skipped by safety gates and require explicit approval to run.")
    if "CLOUDTRAIL_HEADERS_INCOMPLETE" in profile.warnings:
        assumptions.append("CloudTrail-style events do not provide full HTTP header coverage.")
    if "SOURCE_BODY_NOT_AVAILABLE" in profile.warnings:
        assumptions.append("Source object bodies are intentionally unavailable and are not copied or verified.")
    return sorted(set(assumptions))


def _business_flow(default: str, business_context: dict[str, Any]) -> str:
    flows = [str(item) for item in business_context.get("critical_flows", [])]
    if not flows:
        return default
    lowered = default.lower()
    for flow in flows:
        text = flow.lower()
        if any(token in text for token in lowered.split()):
            return flow
    return default


def _empty_results(plan: ProbePlan) -> ProbeResults:
    return ProbeResults(
        result_source="not-run",
        run_id="not-run",
        endpoint_url_redacted="not-run",
        target_bucket_redacted="not-run",
        scratch_prefix=plan.scratch_prefix,
        started_at="not-run",
        finished_at="not-run",
        cleanup={"attempted": False, "succeeded": False, "cleanup_manifest": None},
    )


def _aggregate_status(statuses: list[str]) -> str:
    if not statuses:
        return "NOT_RUN"
    if "FAIL" in statuses:
        return "FAIL"
    if "REVIEW" in statuses:
        return "REVIEW"
    if "SKIP" in statuses:
        return "SKIP"
    if all(status == "PASS" for status in statuses):
        return "PASS"
    return "NOT_RUN"


def _max_severity(current: str, candidate: str) -> str:
    order = {"BLOCKER": 3, "REVIEW": 2, "INFO": 1}
    return candidate if order.get(candidate, 0) > order.get(current, 0) else current


def _write_csv(path: str | Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _csv_value(row.get(column, "")) for column in columns})


def _csv_value(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    if value is None:
        return ""
    return str(value)


def _write_text(path: str | Path, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
