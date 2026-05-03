"""Business-facing decision projection from audit findings."""

from __future__ import annotations

from collections import defaultdict

from .candidates import prerequisite_identity, target_display
from .coverage import decision_impact, decision_status
from .evidence import evidence_strength
from .models import Finding, OwnerMapEntry, OwnerWorkItem, PreflightDecision, PreflightStatus, ServiceFamilyAssessment
from .support_files import owner_contact_by_category


SERVICE_FAMILIES: dict[str, tuple[str, str]] = {
    "dns_resolver": ("name_resolution", "Name Resolution"),
    "directory_service": ("identity_platform", "Identity Platform"),
    "kerberos_service": ("identity_platform", "Identity Platform"),
    "global_catalog": ("identity_platform", "Identity Platform"),
    "database_host": ("data_services", "Data Services"),
    "file_share": ("file_services", "File Services"),
    "license_server": ("license_services", "License Services"),
    "vpn_endpoint": ("remote_access", "Remote Access"),
    "time_service": ("time_services", "Time Services"),
    "other_prerequisite": ("application_prerequisites", "Application Prerequisites"),
}


def service_family_for_category(category: str) -> tuple[str, str]:
    return SERVICE_FAMILIES.get(category, ("application_prerequisites", "Application Prerequisites"))


def build_decisions(findings: list[Finding], *, owner_map: list[OwnerMapEntry] | None = None) -> list[PreflightDecision]:
    owners = owner_contact_by_category(owner_map or [])
    decisions: list[PreflightDecision] = []
    for finding in findings:
        status = decision_status(finding)
        impact = decision_impact(status, finding)
        family, _ = service_family_for_category(finding.category)
        owner = owners.get(finding.category, {})
        decisions.append(
            PreflightDecision(
                prerequisite_id=prerequisite_identity(finding),
                display_name=finding.prerequisite_name,
                category=finding.category,
                service_family=family,
                status=status,
                impact=impact,
                severity=finding.severity,
                confidence=finding.confidence,
                evidence_strength=evidence_strength(finding),
                owner_team=owner.get("owner_team", ""),
                owner_contact=owner.get("contact", ""),
                target=target_display(finding),
                target_ip=finding.prerequisite_target_ip,
                present_in_recovery_set=finding.present_in_recovery_set,
                match_basis=finding.match_basis,
                observed_by=finding.example_protected_systems,
                observed_by_count=finding.observed_by_protected_systems,
                observed_query_count=finding.observed_query_count,
                example_qnames=finding.example_qnames,
                example_answer_names=finding.example_answer_names,
                example_answer_ips=finding.example_answer_ips,
                recommended_action=_recommended_action(status, finding),
                human_question=finding.suggested_human_question,
                audit_reason_codes=finding.reason_codes,
                missing_data=finding.missing_data,
                source_rows=finding.source_rows,
            )
        )
    return sorted(decisions, key=lambda item: (_decision_sort(item.status), item.service_family, item.display_name, item.target))


def build_service_families(decisions: list[PreflightDecision]) -> list[ServiceFamilyAssessment]:
    grouped: dict[str, list[PreflightDecision]] = defaultdict(list)
    for decision in decisions:
        grouped[decision.service_family].append(decision)
    families: list[ServiceFamilyAssessment] = []
    for family, items in grouped.items():
        display_name = next((name for _, (key, name) in SERVICE_FAMILIES.items() if key == family), family.replace("_", " ").title())
        missing_count = sum(1 for item in items if item.status == "missing")
        review_count = sum(1 for item in items if item.status == "review")
        present_count = sum(1 for item in items if item.status == "present")
        accepted_count = sum(1 for item in items if item.status == "accepted_risk")
        status: PreflightStatus = "PASS"
        if any(item.impact == "blocks_recovery_test" for item in items):
            status = "FAIL"
        elif missing_count or review_count or accepted_count:
            status = "REVIEW"
        families.append(
            ServiceFamilyAssessment(
                service_family=family,
                display_name=display_name,
                status=status,
                impact_summary=_family_impact_summary(status, display_name, items),
                owner_teams=_unique([item.owner_team for item in items if item.owner_team]),
                missing_count=missing_count,
                review_count=review_count,
                present_count=present_count,
                accepted_risk_count=accepted_count,
                decisions=[item.prerequisite_id for item in items],
            )
        )
    return sorted(families, key=lambda item: (_family_sort(item.status), item.display_name))


def build_owner_work_items(decisions: list[PreflightDecision]) -> list[OwnerWorkItem]:
    actionable = [item for item in decisions if item.status in {"missing", "review", "accepted_risk"}]
    grouped: dict[tuple[str, str, str], list[PreflightDecision]] = defaultdict(list)
    for decision in actionable:
        target_key = decision.target or decision.display_name
        grouped[(decision.owner_team or "unassigned", decision.service_family, target_key)].append(decision)
    work_items = [_owner_work_item_from_group(items) for items in grouped.values()]
    return sorted(work_items, key=lambda item: (item.owner_team, _decision_sort(item.status), item.service_family, item.prerequisite))


def _owner_work_item_from_group(items: list[PreflightDecision]) -> OwnerWorkItem:
    primary = min(items, key=lambda item: (_decision_sort(item.status), _severity_sort(item.severity), item.display_name))
    return OwnerWorkItem(
        owner_team=primary.owner_team or "unassigned",
        owner_contact=primary.owner_contact,
        service_family=primary.service_family,
        category="|".join(_unique([item.category for item in items])),
        prerequisite=primary.display_name if len(items) == 1 else f"{service_family_for_category(primary.category)[1]}: {primary.target or primary.display_name}",
        prerequisite_id=primary.prerequisite_id,
        status=_highest_status([item.status for item in items]),
        impact=_highest_impact([item.impact for item in items]),
        severity=_highest_severity([item.severity for item in items]),
        evidence_strength=_highest_evidence_strength([item.evidence_strength for item in items]),
        observed_query_count=sum(item.observed_query_count for item in items),
        observed_by_count=max(item.observed_by_count for item in items),
        recommended_action=primary.recommended_action,
        human_question=" | ".join(_unique([item.human_question for item in items if item.human_question])),
        reason_codes=_unique([code for item in items for code in item.audit_reason_codes]),
    )


def _recommended_action(status: str, finding: Finding) -> str:
    if status == "missing":
        return "Decide whether this prerequisite must be added to the recovery set, restored first, or provided by an approved dependency service."
    if status == "review":
        return "Confirm the signal with the owning team and improve evidence before treating it as a recovery-scope requirement."
    if status == "accepted_risk":
        return "Confirm the accepted risk is still valid for this recovery test and that the expiry date has not passed."
    if status == "present":
        return "Keep this prerequisite in the recovery scope and verify startup order during the recovery test."
    return finding.suggested_action or "Review this observation with the responsible owner."


def _family_impact_summary(status: PreflightStatus, display_name: str, items: list[PreflightDecision]) -> str:
    blockers = [item.display_name for item in items if item.impact == "blocks_recovery_test"]
    review = [item.display_name for item in items if item.status == "review"]
    accepted = [item.display_name for item in items if item.status == "accepted_risk"]
    if status == "FAIL":
        return f"{display_name} has recovery-scope gaps that can block application validation: {', '.join(blockers[:3])}."
    if review:
        return f"{display_name} has prerequisites that require owner confirmation before the recovery test: {', '.join(review[:3])}."
    if accepted:
        return f"{display_name} includes accepted-risk items that should be reconfirmed for this preflight."
    return f"{display_name} has no missing required prerequisite in the supplied evidence."


def _decision_sort(status: str) -> int:
    order = {"missing": 0, "review": 1, "accepted_risk": 2, "optional": 3, "present": 4}
    return order.get(status, 5)


def _severity_sort(severity: str) -> int:
    order = {"CRITICAL": 0, "WARNING": 1, "REVIEW": 2, "INFO": 3}
    return order.get(severity, 4)


def _family_sort(status: str) -> int:
    order = {"FAIL": 0, "REVIEW": 1, "PASS": 2}
    return order.get(status, 3)


def _highest_status(values: list[str]) -> str:
    return min(values, key=_decision_sort)


def _highest_impact(values: list[str]) -> str:
    order = {"blocks_recovery_test": 0, "needs_owner_review": 1, "accepted_for_this_preflight": 2, "included_in_recovery_scope": 3, "informational": 4}
    return min(values, key=lambda value: order.get(value, 5))


def _highest_severity(values: list[str]) -> str:
    return min(values, key=_severity_sort)


def _highest_evidence_strength(values: list[str]) -> str:
    order = {"strong": 0, "partial": 1, "weak": 2}
    return min(values, key=lambda value: order.get(value, 3))


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
