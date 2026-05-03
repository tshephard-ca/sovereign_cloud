"""Recovery preflight assessment projection."""

from __future__ import annotations

from . import __version__
from .decision import build_decisions, build_owner_work_items, build_service_families
from .evidence import evidence_improvement_actions
from .models import Finding, OwnerMapEntry, PreflightAssessment, PreflightStatus, Summary


LIMITATIONS = [
    "DNS query evidence shows lookups, not successful network connections.",
    "A preflight assessment is scoped to the supplied inventory, DNS evidence, policy, and time window.",
    "Absent from the recovery set means absent from the supplied inventory, not absent from every backup or platform.",
    "The assessment does not boot systems, orchestrate recovery, query live services, or prove disaster-recovery readiness.",
    "Weak or heuristic findings require owner review before they become recovery-scope requirements.",
]


def build_preflight_assessment(
    *,
    findings: list[Finding],
    summary: Summary,
    owner_map: list[OwnerMapEntry] | None = None,
) -> PreflightAssessment:
    decisions = build_decisions(findings, owner_map=owner_map)
    service_families = build_service_families(decisions)
    owner_work_items = build_owner_work_items(decisions)
    decision = _overall_decision(summary, service_families)
    gap_decisions = sorted(
        [
            item
            for item in decisions
            if item.status in {"missing", "review"} and item.impact in {"blocks_recovery_test", "needs_owner_review"}
        ],
        key=_gap_sort,
    )
    top_gaps = _unique([item.display_name for item in gap_decisions])[:10]
    return PreflightAssessment(
        schema_version="1.0",
        tool_version=summary.tool_version or __version__,
        recovery_set=summary.recovery_set,
        decision=decision,
        business_impact=_business_impact(decision, top_gaps),
        executive_summary=_executive_summary(summary, service_families, owner_work_items),
        input_counts=summary.input,
        finding_counts=summary.findings,
        service_families=service_families,
        decisions=decisions,
        owner_work_items=owner_work_items,
        evidence_quality=summary.evidence_quality,
        evidence_improvement_actions=evidence_improvement_actions(summary),
        top_recovery_scope_gaps=top_gaps,
        recommended_next_questions=summary.recommended_next_questions,
        limitations=LIMITATIONS,
        warnings=summary.warnings,
        assumptions=summary.assumptions,
        run_metadata=summary.run_metadata,
    )


def _overall_decision(summary: Summary, service_families: list[object]) -> PreflightStatus:
    if summary.lint_status == "FAIL":
        return "FAIL"
    if any(getattr(item, "status", "") == "FAIL" for item in service_families):
        return "FAIL"
    if summary.lint_status == "REVIEW" or any(getattr(item, "status", "") == "REVIEW" for item in service_families):
        return "REVIEW"
    return "PASS"


def _business_impact(decision: PreflightStatus, top_gaps: list[str]) -> str:
    if decision == "FAIL":
        detail = f" Top gaps: {', '.join(top_gaps[:5])}." if top_gaps else ""
        return "The declared recovery set has prerequisite gaps that can delay or block application validation during a recovery test." + detail
    if decision == "REVIEW":
        detail = f" Review first: {', '.join(top_gaps[:5])}." if top_gaps else ""
        return "The supplied evidence is incomplete or has review-only signals; owner confirmation is needed before treating the scope as ready for test." + detail
    return "No required prerequisite gap was found in the supplied evidence; this is a preflight signal, not proof of recovery readiness."


def _executive_summary(summary: Summary, service_families: list[object], owner_work_items: list[object]) -> list[str]:
    failing = [getattr(item, "display_name", "") for item in service_families if getattr(item, "status", "") == "FAIL"]
    review = [getattr(item, "display_name", "") for item in service_families if getattr(item, "status", "") == "REVIEW"]
    lines = [
        f"Assessment decision: {summary.lint_status}.",
        f"Protected systems in evidence: {summary.input.get('protected_systems', 0)}; recovery-set systems: {summary.input.get('recovery_set_systems', 0)}; DNS rows in window: {summary.input.get('dns_log_rows_in_window', 0)}.",
    ]
    if failing:
        lines.append(f"Blocking service families: {', '.join(failing)}.")
    if review:
        lines.append(f"Service families requiring owner review: {', '.join(review)}.")
    if owner_work_items:
        owners = sorted({getattr(item, "owner_team", "") for item in owner_work_items if getattr(item, "owner_team", "")})
        lines.append(f"Owner worklist items: {len(owner_work_items)} across {len(owners)} owner teams.")
    if summary.evidence_quality.get("status"):
        lines.append(f"Evidence quality: {summary.evidence_quality.get('status')}.")
    return lines


def _gap_sort(item: object) -> tuple[int, int, str]:
    impact_order = {"blocks_recovery_test": 0, "needs_owner_review": 1}
    severity_order = {"CRITICAL": 0, "WARNING": 1, "REVIEW": 2, "INFO": 3}
    return (
        impact_order.get(getattr(item, "impact", ""), 9),
        severity_order.get(getattr(item, "severity", ""), 9),
        getattr(item, "display_name", ""),
    )


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
