"""Evidence-strength scoring and improvement actions."""

from __future__ import annotations

from .models import EvidenceImprovementAction, EvidenceStrength, Finding, Summary


def evidence_strength(finding: Finding) -> EvidenceStrength:
    if finding.confidence == "LOW":
        return "weak"
    if finding.missing_data or "ANSWER_DATA_MISSING" in finding.reason_codes or "HEURISTIC_ONLY_REVIEW" in finding.reason_codes:
        return "partial"
    if finding.confidence == "HIGH":
        return "strong"
    return "partial"


def evidence_improvement_actions(summary: Summary) -> list[EvidenceImprovementAction]:
    quality = summary.evidence_quality or {}
    metrics = quality.get("metrics", {}) if isinstance(quality.get("metrics", {}), dict) else {}
    input_audit = quality.get("input_audit", {}) if isinstance(quality.get("input_audit", {}), dict) else {}
    actions: list[EvidenceImprovementAction] = []
    if metrics.get("mapped_client_identity_pct", 100) < 95:
        actions.append(
            EvidenceImprovementAction(
                priority="HIGH",
                action="Add or correct inventory aliases, FQDNs, and IP addresses so DNS clients map to protected systems.",
                reason="Unmapped DNS clients weaken ownership and impact routing.",
                related_metric="mapped_client_identity_pct",
            )
        )
    if metrics.get("answer_ip_coverage_pct", 100) < 80:
        actions.append(
            EvidenceImprovementAction(
                priority="HIGH",
                action="Provide DNS answer data or an offline answer map for in-scope query names.",
                reason="Missing answer data can identify a dependency category without identifying the recoverable target.",
                related_metric="answer_ip_coverage_pct",
            )
        )
    if quality.get("answer_map_enriched_rows", 0):
        actions.append(
            EvidenceImprovementAction(
                priority="LOW",
                action="Keep the offline answer map with the evidence package and document its export source.",
                reason="Answer-map enrichment improves target matching, but reviewers need provenance for the supplemental data.",
                related_metric="answer_map_enriched_rows",
            )
        )
    if not _resolver_identity_known(summary):
        actions.append(
            EvidenceImprovementAction(
                priority="HIGH",
                action="Declare required resolvers in required_resolvers.yml or include resolver identity in the DNS export.",
                reason="A recovery set cannot be assessed for name-resolution coverage when resolver identity is unknown.",
                related_metric="resolver_identity",
            )
        )
    if metrics.get("window_coverage_pct", 100) < 50:
        actions.append(
            EvidenceImprovementAction(
                priority="MEDIUM",
                action="Analyze a wider DNS evidence window and compare it with the default recovery-test window.",
                reason="Short windows may miss weekly, monthly, startup-only, or failover-only prerequisites.",
                related_metric="window_coverage_pct",
            )
        )
    if input_audit.get("missing_owner_team_rows", 0):
        actions.append(
            EvidenceImprovementAction(
                priority="MEDIUM",
                action="Populate owner_team in the backup inventory and owner_map.csv.",
                reason="Owner routing is less actionable when protected systems or prerequisite categories lack owners.",
                related_metric="missing_owner_team_rows",
            )
        )
    if input_audit.get("missing_business_service_rows", 0) or input_audit.get("missing_criticality_rows", 0) or input_audit.get("missing_recovery_tier_rows", 0):
        actions.append(
            EvidenceImprovementAction(
                priority="MEDIUM",
                action="Populate business_service, criticality, and recovery_tier for protected inventory rows.",
                reason="Business impact is more useful when findings can be sorted by service criticality and recovery expectations.",
                related_metric="business_context_completeness",
            )
        )
    if input_audit.get("duplicate_fqdn_count", 0) or input_audit.get("duplicate_ip_count", 0):
        actions.append(
            EvidenceImprovementAction(
                priority="MEDIUM",
                action="Resolve duplicate FQDN and IP entries in the backup inventory.",
                reason="Duplicate identities can create ambiguous recovery-set matches.",
                related_metric="inventory_duplicates",
            )
        )
    if not actions and quality.get("status") == "GOOD":
        actions.append(
            EvidenceImprovementAction(
                priority="LOW",
                action="Keep the input package with the preflight record so future runs can compare evidence quality and scope.",
                reason="The supplied evidence is strong enough for review, but it remains a point-in-time preflight artifact.",
                related_metric="evidence_quality_status",
            )
        )
    return actions


def _resolver_identity_known(summary: Summary) -> bool:
    return "DNS_RESOLVER_IDENTITY_UNKNOWN" not in summary.warnings
