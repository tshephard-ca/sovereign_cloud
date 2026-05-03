"""Coverage decisions for observed recovery prerequisites."""

from __future__ import annotations

from .models import DecisionImpact, DecisionStatus, Finding


def decision_status(finding: Finding) -> DecisionStatus:
    if finding.finding_code == "ACCEPTED_RISK_APPLIED" or "ACCEPTED_RISK_APPLIED" in finding.reason_codes:
        return "accepted_risk"
    if finding.present_in_recovery_set:
        return "present"
    if finding.finding_code == "OPTIONAL_PREREQ_OBSERVED" or not _required_reason_set(finding):
        return "optional"
    if finding.severity in {"CRITICAL", "WARNING"}:
        return "missing"
    return "review"


def decision_impact(status: DecisionStatus, finding: Finding) -> DecisionImpact:
    if status == "missing" and finding.severity == "CRITICAL":
        return "blocks_recovery_test"
    if status in {"missing", "review"}:
        return "needs_owner_review"
    if status == "accepted_risk":
        return "accepted_for_this_preflight"
    if status == "present":
        return "included_in_recovery_scope"
    return "informational"


def _required_reason_set(finding: Finding) -> bool:
    return "OPTIONAL_PREREQ_OBSERVED" not in finding.reason_codes
