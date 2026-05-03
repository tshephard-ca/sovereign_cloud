from __future__ import annotations

from typing import Any


CONTRACT_SCHEMAS: dict[str, dict[str, Any]] = {
    "evidence-bundle-manifest": {
        "schema_version": "1.0",
        "required": [
            "schema_version",
            "collector_version",
            "collected_at",
            "redaction_mode",
            "safe_host_facts",
            "commands",
            "files",
            "bundle_fingerprint",
        ],
        "file_required": ["path", "size_bytes", "sha256"],
        "command_required": ["file", "command", "returncode", "status"],
    },
    "storage-profile-snapshot": {
        "schema_version": "1.0",
        "required": ["schema_version", "path", "sha256", "captured_at", "fingerprint", "origin", "storage_classes"],
    },
    "path-purpose": {
        "schema_version": "1.0",
        "required": ["paths"],
        "path_required": ["path", "purpose", "read_write_pattern", "writer_topology", "owner_confidence"],
    },
    "engine-decision-record": {
        "schema_version": "1.0",
        "required": [
            "schema_version",
            "captured_at",
            "fit_status",
            "required_access_mode",
            "required_volume_mode",
            "preferred_storage_kind",
            "reason_codes",
            "blockers",
            "analysis",
        ],
    },
    "expert-review": {
        "schema_version": "1.0",
        "required": ["reviewer_id", "fit_status"],
        "recommended": [
            "reviewed_at",
            "required_access_mode",
            "required_volume_mode",
            "preferred_storage_kind",
            "blockers",
            "confidence",
            "notes",
        ],
    },
    "adjudication": {
        "schema_version": "1.0",
        "required": ["adjudicator_id", "fit_status", "rationale"],
        "recommended": ["adjudicated_at", "required_access_mode", "required_volume_mode", "preferred_storage_kind"],
    },
    "outcome-record": {
        "schema_version": "1.0",
        "required": ["status"],
        "valid_statuses": [
            "onboarded_successfully",
            "storage_fit_confirmed",
            "blocked_by_storage",
            "failed_storage_assumption",
            "storage_rework_required",
            "blocked_by_non_storage",
            "not_attempted",
            "unknown",
        ],
        "recommended": ["recorded_at", "target_storage_class", "observed_storage_blockers", "notes"],
    },
    "business-impact-record": {
        "schema_version": "1.0",
        "required": ["recorded_at"],
        "recommended": [
            "assessment_minutes",
            "expert_review_minutes",
            "blocker_found_before_pilot",
            "failed_pilot_avoided",
            "platform_gap_identified",
            "decision",
        ],
    },
    "corpus-case": {
        "schema_version": "1.0",
        "required": [
            "schema_version",
            "id",
            "data_origin",
            "profile_origin",
            "lifecycle_state",
            "storage_profile",
            "engine_decision",
        ],
        "sections": [
            "bundle",
            "storage_profile_snapshot",
            "engine_decision",
            "expert_reviews",
            "adjudication",
            "outcomes",
            "business_impact",
        ],
    },
    "calibration-report": {
        "schema_version": "1.0",
        "required": [
            "schema_version",
            "case_count",
            "trusted_label_count",
            "outcome_linked_case_count",
            "outcome_metrics",
            "business_impact_metrics",
            "readiness",
        ],
    },
    "decision-validation-report": {
        "schema_version": "1.0",
        "required": ["valid", "issues", "warnings"],
    },
    "input-realism-report": {
        "schema_version": "1.0",
        "required": [
            "schema_version",
            "valid",
            "issues",
            "warnings",
            "bundle_validation",
            "network_filesystem_mounts",
            "useful_processes",
        ],
    },
    "corpus-coverage-report": {
        "schema_version": "1.0",
        "required": [
            "schema_version",
            "family_counts",
            "reason_code_counts",
            "outcome_counts",
            "capability_counts",
            "family_coverage_gaps",
            "reason_coverage_gaps",
        ],
    },
    "outcome-request-report": {
        "schema_version": "1.0",
        "required": ["schema_version", "requests"],
    },
    "evaluation-comparison-report": {
        "schema_version": "1.0",
        "required": [
            "schema_version",
            "old_readiness",
            "new_readiness",
            "regressions",
            "release_gate_passed",
        ],
    },
    "tool-preflight-report": {
        "schema_version": "1.0",
        "required": ["schema_version", "valid", "missing_required_tools", "missing_optional_tools", "tools"],
    },
    "evidence-mode-report": {
        "schema_version": "1.0",
        "required": ["schema_version", "modes"],
    },
    "quality-gate-report": {
        "schema_version": "1.0",
        "required": ["schema_version", "mode", "gate_status", "passed", "issues", "warnings"],
    },
    "audit-manifest": {
        "schema_version": "1.0",
        "required": ["schema_version", "created_at", "audit_dir", "file_count", "files", "audit_fingerprint"],
    },
    "decision-diff-report": {
        "schema_version": "1.0",
        "required": ["schema_version", "changed", "scalar_changes", "set_changes"],
    },
    "evidence-question-report": {
        "schema_version": "1.0",
        "required": ["schema_version", "decision", "fit_status", "question_count", "questions"],
    },
    "coverage-plan-report": {
        "schema_version": "1.0",
        "required": ["schema_version", "coverage", "requests"],
    },
    "business-impact-summary": {
        "schema_version": "1.0",
        "required": [
            "schema_version",
            "case_count",
            "impact_record_count",
            "high_quality_impact_record_count",
            "claim_status",
        ],
    },
    "calibration-action-report": {
        "schema_version": "1.0",
        "required": ["schema_version", "readiness_level", "actions", "mismatch_count"],
    },
    "proprietary-scan-report": {
        "schema_version": "1.0",
        "required": ["schema_version", "valid", "issues", "warnings", "matches"],
    },
    "full-coverage-lab-summary": {
        "schema_version": "1.0",
        "required": ["schema_version", "generated_at", "data_origin", "case_count", "family_targets", "cases"],
    },
    "owner-evidence-template": {
        "schema_version": "1.0",
        "required": [
            "schema_version",
            "collection_window",
            "growth_and_retention",
            "metadata_shape",
            "write_consistency",
            "application_lifecycle",
            "multi_vm_relationships",
            "profile_attestation",
        ],
    },
    "attestation-template": {
        "schema_version": "1.0",
        "required": ["schema_version", "kind", "subject", "attester_id", "attested_at", "confidence", "claims"],
    },
    "attestation-validation-report": {
        "schema_version": "1.0",
        "required": ["schema_version", "valid", "kind", "issues", "warnings"],
    },
    "real-world-evidence-contract": {
        "schema_version": "1.0",
        "required": [
            "schema_version",
            "purpose",
            "generated_data_boundary",
            "required_for_business_impact",
            "required_for_calibration",
            "claim_rules",
        ],
    },
    "operating-model-template": {
        "schema_version": "1.0",
        "required": ["schema_version", "roles", "workflow_states", "sla_defaults", "gate_policy"],
    },
    "timestamp-attestation-template": {
        "schema_version": "1.0",
        "required": [
            "schema_version",
            "audit_fingerprint",
            "external_timestamp_reference",
            "timestamp_provider_or_repository",
            "recorded_at",
        ],
    },
    "evidence-repository-export": {
        "schema_version": "1.0",
        "required": ["schema_version", "created_at", "source_audit_dir", "audit_fingerprint", "repository_contract", "files"],
    },
    "chain-of-custody-record": {
        "schema_version": "1.0",
        "required": ["schema_version", "created_at", "audit_dir", "audit_fingerprint", "file_count", "warnings"],
    },
    "audit-manifest-signature": {
        "schema_version": "1.0",
        "required": ["schema_version", "created_at", "algorithm", "manifest", "manifest_sha256", "signature", "key_id"],
    },
    "gap-closure-lab-summary": {
        "schema_version": "1.0",
        "required": [
            "schema_version",
            "generated_at",
            "data_origin",
            "case_count",
            "gap_count",
            "closed_gap_count",
            "fit_status_counts",
            "gap_matrix",
        ],
    },
    "trend-report": {
        "schema_version": "1.0",
        "required": ["schema_version", "decision_count", "rows", "transitions", "trend_flags"],
    },
    "followup-sla-report": {
        "schema_version": "1.0",
        "required": ["schema_version", "corpus_dir", "item_count", "items"],
    },
    "handoff-bundle-report": {
        "schema_version": "1.0",
        "required": ["schema_version", "audit_dir", "output", "file_count", "audit_fingerprint"],
    },
}


def get_contract_schema(name: str | None = None) -> dict[str, Any]:
    if name is None:
        return {"schema_version": "1.0", "schemas": sorted(CONTRACT_SCHEMAS)}
    if name not in CONTRACT_SCHEMAS:
        raise KeyError(name)
    return CONTRACT_SCHEMAS[name]
