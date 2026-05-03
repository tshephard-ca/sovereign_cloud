from __future__ import annotations

import json
import re
import shutil
import zipfile
import hmac
import hashlib
from pathlib import Path
from typing import Any

import yaml

from .app_metadata import load_path_purpose
from .classify_mounts import classify_candidate_mounts
from .config import DEFAULT_THRESHOLDS
from .corpus import evaluate_corpus
from .origins import is_generated_origin
from .parse_df import parse_df_file
from .parse_fstab import parse_fstab_file
from .parse_iostat import parse_iostat_file
from .parse_mount import parse_mount_file
from .workflow import corpus_coverage, now_utc, sha256_file, validate_case


REQUIRED_TOOLS = {
    "df": "core filesystem capacity evidence",
    "mount": "core mount table evidence",
    "cat": "core fstab collection",
    "ps": "core process evidence",
}

OPTIONAL_TOOLS = {
    "iostat": "latency and utilization sample evidence",
    "findmnt": "mount topology evidence",
    "lsblk": "block device lineage evidence",
    "blkid": "block identifier evidence",
    "pvs": "physical volume evidence",
    "vgs": "volume group evidence",
    "lvs": "logical volume evidence",
    "du": "owner-declared path size evidence",
}


def tool_preflight() -> dict[str, Any]:
    rows = []
    missing_required = []
    for name, purpose in REQUIRED_TOOLS.items():
        path = shutil.which(name)
        rows.append({"tool": name, "required": True, "available": bool(path), "path": path, "purpose": purpose})
        if not path:
            missing_required.append(name)
    missing_optional = []
    for name, purpose in OPTIONAL_TOOLS.items():
        path = shutil.which(name)
        rows.append({"tool": name, "required": False, "available": bool(path), "path": path, "purpose": purpose})
        if not path:
            missing_optional.append(name)
    available_optional = len(OPTIONAL_TOOLS) - len(missing_optional)
    return {
        "schema_version": "1.0",
        "checked_at": now_utc(),
        "valid": not missing_required,
        "missing_required_tools": missing_required,
        "missing_optional_tools": missing_optional,
        "optional_tool_coverage": round(available_optional / len(OPTIONAL_TOOLS), 3),
        "tools": rows,
    }


def evidence_modes() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "modes": [
            {
                "name": "minimal",
                "purpose": "Basic local storage shape check.",
                "required_inputs": ["df.txt", "mount.txt", "fstab.txt", "iostat.txt", "ps.txt", "storage-profile.yml"],
                "business_use": "Initial triage only.",
            },
            {
                "name": "standard",
                "purpose": "Adds mount and block topology where available.",
                "required_inputs": [
                    "minimal inputs",
                    "findmnt.json",
                    "lsblk.json",
                    "inode-df.txt",
                    "du-summary.txt for declared data paths",
                ],
                "business_use": "Storage review handoff when warnings are resolved or accepted.",
            },
            {
                "name": "owner_enriched",
                "purpose": "Adds workload-owner path purpose, collection window, and growth metadata.",
                "required_inputs": ["standard inputs", "path-purpose.yml", "owner review fields"],
                "business_use": "Business review candidate, still not calibration evidence by itself.",
            },
            {
                "name": "calibration_grade",
                "purpose": "Adds independent expert review, adjudication when needed, decisive outcome, and impact record.",
                "required_inputs": [
                    "owner_enriched inputs",
                    "two structured expert reviews or adjudication",
                    "decisive storage-relevant outcome",
                    "business impact record with source and confidence",
                ],
                "business_use": "Eligible for empirical calibration and business-impact reporting.",
            },
        ],
    }


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def path_purpose_template(bundle_dir: Path) -> dict[str, Any]:
    df_path = bundle_dir / "df.txt"
    mount_path = bundle_dir / "mount.txt"
    fstab_path = bundle_dir / "fstab.txt"
    iostat_path = bundle_dir / "iostat.txt"
    if not df_path.exists() or not mount_path.exists():
        raise ValueError("bundle must contain df.txt and mount.txt")
    df_entries, _ = parse_df_file(df_path)
    mount_entries, _ = parse_mount_file(mount_path)
    fstab_entries = parse_fstab_file(fstab_path)[0] if fstab_path.exists() else []
    iostat_samples = parse_iostat_file(iostat_path)[0] if iostat_path.exists() else {}
    candidates, warnings, _ = classify_candidate_mounts(
        df_entries,
        mount_entries,
        fstab_entries,
        iostat_samples,
        DEFAULT_THRESHOLDS,
        [],
    )
    return {
        "schema_version": "1.0",
        "generated_at": now_utc(),
        "source_bundle": str(bundle_dir),
        "warnings": warnings,
        "paths": [
            {
                "path": candidate.mount_path,
                "purpose": "owner_required",
                "read_write_pattern": "owner_required",
                "writer_topology": "owner_required",
                "owner_confidence": "REQUIRES_OWNER",
                "observed_role": candidate.inferred_role,
                "observed_fs_type": candidate.fs_type,
                "observed_used_gib": candidate.used_gib,
                "candidate_score": candidate.candidate_score,
                "false_positive_risk": candidate.false_positive_risk,
                "notes": "Generated from local evidence. A workload owner must confirm purpose and ownership.",
            }
            for candidate in candidates
        ],
    }


def quality_gate(
    *,
    input_realism: Path | None = None,
    decision_validation: Path | None = None,
    case_validation: Path | None = None,
    corpus_evaluation: Path | None = None,
    gate_config: Path | None = None,
    mode: str = "business_review",
) -> dict[str, Any]:
    config = {
        "min_core_score": 1.0,
        "min_topology_score": 0.7,
        "min_bundle_quality": 0.85,
        "block_generic_profile": True,
        "block_path_purpose_mismatch": True,
        "require_decision_valid": True,
        "require_case_valid": True,
        "require_trusted_label_for_outcome_request": False,
        "require_calibration_ready_for_release": True,
        "block_research_only_corpus_for_business_review": True,
    }
    config.update(_load_yaml(gate_config))
    issues: list[str] = []
    warnings: list[str] = []

    def load_report(path: Path | None, missing_code: str) -> dict[str, Any]:
        if path is None:
            return {}
        if not path.exists():
            issues.append(missing_code)
            return {}
        return _load_json(path)

    inputs = load_report(input_realism, "INPUT_REALISM_REPORT_MISSING")
    decision = load_report(decision_validation, "DECISION_VALIDATION_REPORT_MISSING")
    case = load_report(case_validation, "CASE_VALIDATION_REPORT_MISSING")
    corpus = load_report(corpus_evaluation, "CORPUS_EVALUATION_REPORT_MISSING")

    if inputs:
        if not inputs.get("valid", False):
            issues.append("INPUT_REALISM_INVALID")
        bundle = inputs.get("bundle_validation") or {}
        if bundle.get("core_completeness_score", 0) < float(config["min_core_score"]):
            issues.append("CORE_EVIDENCE_BELOW_GATE")
        if bundle.get("topology_completeness_score", 0) < float(config["min_topology_score"]):
            issues.append("TOPOLOGY_EVIDENCE_BELOW_GATE")
        if bundle.get("overall_bundle_quality_score", 0) < float(config["min_bundle_quality"]):
            issues.append("BUNDLE_QUALITY_BELOW_GATE")
        input_warnings = set(inputs.get("warnings") or [])
        if config.get("block_generic_profile") and "PROFILE_APPEARS_TO_BE_EXAMPLE_GENERIC" in input_warnings:
            issues.append("GENERIC_PROFILE_BLOCKED_FOR_BUSINESS_REVIEW")
        if config.get("block_path_purpose_mismatch") and "DECLARED_APP_PATH_NOT_OBSERVED_IN_MOUNT_OUTPUT" in input_warnings:
            issues.append("PATH_PURPOSE_MISMATCH_BLOCKED_FOR_BUSINESS_REVIEW")
    else:
        warnings.append("INPUT_REALISM_REPORT_NOT_SUPPLIED")

    if decision:
        if config.get("require_decision_valid") and not decision.get("valid", False):
            issues.append("DECISION_VALIDATION_FAILED")
    else:
        warnings.append("DECISION_VALIDATION_REPORT_NOT_SUPPLIED")

    if case:
        if config.get("require_case_valid") and not case.get("valid", False):
            issues.append("CASE_VALIDATION_FAILED")
        if mode in {"calibration", "release"} and not case.get("calibration_ready", False):
            issues.append("CASE_NOT_CALIBRATION_READY")
        elif not case.get("trusted_label", False):
            warnings.append("CASE_HAS_NO_TRUSTED_LABEL")
    elif mode in {"calibration", "release"}:
        issues.append("CASE_VALIDATION_REQUIRED_FOR_CALIBRATION_OR_RELEASE")

    if corpus:
        readiness = corpus.get("readiness") or {}
        if mode == "release" and readiness.get("level") != "PRODUCTION_READY":
            issues.append("CORPUS_NOT_PRODUCTION_READY")
        elif mode == "calibration" and readiness.get("level") == "RESEARCH_ONLY":
            issues.append("CORPUS_RESEARCH_ONLY_BLOCKED_FOR_CALIBRATION")
        elif (
            mode == "business_review"
            and readiness.get("level") == "RESEARCH_ONLY"
            and config.get("block_research_only_corpus_for_business_review")
        ):
            issues.append("CORPUS_RESEARCH_ONLY_BLOCKED_FOR_BUSINESS_REVIEW")
        elif readiness.get("level") == "RESEARCH_ONLY":
            warnings.append("CORPUS_RESEARCH_ONLY")
    elif mode == "release":
        issues.append("CORPUS_EVALUATION_REQUIRED_FOR_RELEASE")

    status = "PASS" if not issues else ("REVIEW" if mode == "business_review" else "FAIL")
    return {
        "schema_version": "1.0",
        "mode": mode,
        "gate_status": status,
        "passed": status == "PASS",
        "issues": issues,
        "warnings": warnings,
        "config": config,
    }


def audit_manifest(audit_dir: Path) -> dict[str, Any]:
    files = []
    for path in sorted(audit_dir.rglob("*")):
        if path.is_file():
            files.append(
                {
                    "path": str(path.relative_to(audit_dir)),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    fingerprint_source = "\n".join(f"{item['path']}:{item['sha256']}" for item in files)
    import hashlib

    return {
        "schema_version": "1.0",
        "created_at": now_utc(),
        "audit_dir": str(audit_dir),
        "file_count": len(files),
        "files": files,
        "audit_fingerprint": hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest(),
        "tamper_evidence": "sha256 chain only; no signing key is used by this local-only tool",
    }


def decision_diff(old_path: Path, new_path: Path) -> dict[str, Any]:
    old = _load_json(old_path)
    new = _load_json(new_path)
    scalar_fields = [
        "fit_status",
        "recommended_storage_class",
        "required_access_mode",
        "required_volume_mode",
        "preferred_storage_kind",
        "storage_request_gib",
        "capacity_risk",
        "latency_risk",
        "confidence",
    ]
    changes = []
    for field in scalar_fields:
        if old.get(field) != new.get(field):
            changes.append({"field": field, "old": old.get(field), "new": new.get(field)})

    def set_delta(field: str) -> dict[str, Any]:
        old_values = set(old.get(field) or [])
        new_values = set(new.get(field) or [])
        return {
            "field": field,
            "added": sorted(new_values - old_values),
            "removed": sorted(old_values - new_values),
        }

    list_changes = [set_delta("reason_codes"), set_delta("warnings"), set_delta("blockers")]
    return {
        "schema_version": "1.0",
        "changed": bool(changes or any(item["added"] or item["removed"] for item in list_changes)),
        "scalar_changes": changes,
        "set_changes": list_changes,
    }


def export_evidence_questions(decision_path: Path) -> dict[str, Any]:
    decision = _load_json(decision_path)
    questions = ((decision.get("analysis") or {}).get("evidence_questions") or [])
    if not questions and decision.get("fit_status") == "REVIEW":
        questions = [
            {
                "id": "manual_review_required",
                "priority": "HIGH",
                "question": "What missing local or owner evidence would resolve the REVIEW decision?",
                "why_it_matters": "The decision includes REVIEW risk signals but no structured question was emitted.",
                "would_change": ["fit_status", "confidence"],
                "related_reason_codes": decision.get("reason_codes", []),
                "suggested_local_evidence": [],
            }
        ]
    return {
        "schema_version": "1.0",
        "decision": str(decision_path),
        "fit_status": decision.get("fit_status"),
        "question_count": len(questions),
        "questions": questions,
    }


def coverage_plan(corpus_dir: Path) -> dict[str, Any]:
    coverage = corpus_coverage(corpus_dir)
    requests = []
    for family, count in coverage.get("family_coverage_gaps", {}).items():
        if count:
            requests.append(
                {
                    "kind": "workload_family",
                    "target": family,
                    "needed_cases": count,
                    "required_evidence_level": "calibration_grade",
                }
            )
    for code, count in coverage.get("reason_coverage_gaps", {}).items():
        if count:
            requests.append(
                {
                    "kind": "reason_code",
                    "target": code,
                    "needed_cases": count,
                    "required_evidence_level": "calibration_grade",
                }
            )
    return {
        "schema_version": "1.0",
        "coverage": coverage,
        "requests": requests,
        "note": "Synthetic cases can close parser and regression gaps, but calibration-grade requests require real bundles, expert labels, decisive outcomes, and impact records.",
    }


def business_impact_summary(corpus_dir: Path, baseline: Path | None = None) -> dict[str, Any]:
    baseline_data = _load_yaml(baseline) if baseline else {}
    baseline_assessment_minutes = baseline_data.get("baseline_assessment_minutes_per_case")
    cases = []
    total_assessment = 0
    total_review = 0
    impact_records = 0
    high_quality_records = 0
    generated_impact_records = 0
    measured_high_quality_records = 0
    for path in sorted(corpus_dir.glob("*.yml")):
        validation = validate_case(path)
        case = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        generated_case = is_generated_origin(case.get("data_origin")) or case.get("case_kind") == "generated_full_coverage"
        impacts = case.get("business_impact") or []
        impact_records += len(impacts)
        if generated_case:
            generated_impact_records += len(impacts)
        if validation.get("business_impact_quality_score", 0) >= 70:
            high_quality_records += len(impacts)
            if not generated_case:
                measured_high_quality_records += len(impacts)
        for impact in impacts:
            total_assessment += int(impact.get("assessment_minutes") or 0)
            total_review += int(impact.get("expert_review_minutes") or 0)
        cases.append({"case_id": case.get("id"), "validation": validation})
    baseline_total = None
    operational_minutes_delta = None
    if baseline_assessment_minutes is not None:
        baseline_total = int(baseline_assessment_minutes) * len(cases)
        operational_minutes_delta = baseline_total - total_assessment
    return {
        "schema_version": "1.0",
        "case_count": len(cases),
        "impact_record_count": impact_records,
        "high_quality_impact_record_count": high_quality_records,
        "generated_impact_record_count": generated_impact_records,
        "measured_high_quality_impact_record_count": measured_high_quality_records,
        "assessment_minutes_total": total_assessment,
        "expert_review_minutes_total": total_review,
        "baseline_assessment_minutes_total": baseline_total,
        "operational_minutes_delta": operational_minutes_delta,
        "claim_status": (
            "MEASURED_OPERATIONAL"
            if measured_high_quality_records
            else ("SIMULATED_ONLY" if high_quality_records else "EVIDENCE_MISSING")
        ),
        "cases": cases,
    }


def calibration_actions(corpus_evaluation: Path) -> dict[str, Any]:
    report = _load_json(corpus_evaluation)
    actions = []
    readiness = report.get("readiness") or {}
    for blocker in readiness.get("blockers", []):
        if blocker == "INSUFFICIENT_OUTCOME_LINKED_CASES":
            actions.append("Add decisive outcome records for trusted-label cases.")
        elif blocker == "INSUFFICIENT_OUTCOME_COVERAGE":
            actions.append("Prioritize outcome follow-up for older reviewed cases.")
        elif blocker == "INSUFFICIENT_TRUSTED_LABEL_COVERAGE":
            actions.append("Add independent expert reviews or adjudication before outcome requests.")
        elif blocker == "PASS_STORAGE_FAILURE_RATE_TOO_HIGH":
            actions.append("Review false PASS cases and tighten PASS gates or reason-code thresholds.")
        else:
            actions.append(f"Resolve readiness blocker: {blocker}.")
    if report.get("mismatches"):
        actions.append("Inspect mismatched cases and add regression tests before changing thresholds.")
    return {
        "schema_version": "1.0",
        "readiness_level": readiness.get("level"),
        "actions": actions,
        "mismatch_count": len(report.get("mismatches") or []),
    }


def proprietary_scan(paths: list[Path], banned_terms: Path | None = None) -> dict[str, Any]:
    if banned_terms is None:
        return {
            "schema_version": "1.0",
            "valid": False,
            "issues": ["BANNED_TERMS_FILE_REQUIRED"],
            "warnings": ["No default proprietary-name list is bundled."],
            "matches": [],
        }
    terms = [
        line.strip()
        for line in banned_terms.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not terms:
        return {
            "schema_version": "1.0",
            "valid": False,
            "issues": ["BANNED_TERMS_FILE_EMPTY"],
            "warnings": [],
            "matches": [],
        }
    patterns = [(term, re.compile(re.escape(term), re.IGNORECASE)) for term in terms]
    matches = []
    for root in paths:
        files = [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()]
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                for term, pattern in patterns:
                    if pattern.search(line):
                        matches.append({"path": str(path), "line": line_no, "term": term})
    return {
        "schema_version": "1.0",
        "valid": not matches,
        "issues": ["BANNED_TERM_MATCH"] if matches else [],
        "warnings": [],
        "matches": matches,
    }


def owner_evidence_template(bundle_dir: Path | None = None) -> dict[str, Any]:
    candidate_paths: list[str] = []
    if bundle_dir is not None and bundle_dir.exists():
        try:
            candidate_paths = [item["path"] for item in path_purpose_template(bundle_dir).get("paths", [])]
        except ValueError:
            candidate_paths = []
    return {
        "schema_version": "1.0",
        "generated_at": now_utc(),
        "candidate_paths": candidate_paths,
        "collection_window": {
            "workload_state": "idle | normal_business | peak | backup | batch | maintenance | incident",
            "started_at": "YYYY-MM-DDTHH:MM:SSZ",
            "ended_at": "YYYY-MM-DDTHH:MM:SSZ",
            "owner_confidence": "LOW | MEDIUM | HIGH",
        },
        "growth_and_retention": {
            "growth_observation_window_days": None,
            "estimated_growth_gib_per_month": None,
            "retention_policy": "owner_required",
            "purge_or_archive_policy": "owner_required",
            "compression_or_dedupe_expected": "unknown",
        },
        "metadata_shape": {
            "small_file_heavy": "unknown",
            "approximate_file_count": None,
            "largest_directory_fanout": None,
            "notes": "",
        },
        "write_consistency": {
            "requires_fsync_durability": "unknown",
            "uses_file_locks": "unknown",
            "crash_recovery_expectation": "owner_required",
            "raw_device_requirement_confirmed": "unknown",
        },
        "application_lifecycle": {
            "backup_window": "owner_required",
            "restore_tested": "unknown",
            "failover_topology": "single_vm | active_passive | active_active | unknown",
            "batch_or_maintenance_jobs": [],
        },
        "multi_vm_relationships": {
            "other_vms_share_storage": "unknown",
            "shared_paths": [],
            "writer_count": None,
        },
        "profile_attestation": {
            "profile_owner": "owner_required",
            "profile_current_as_of": "YYYY-MM-DD",
            "quota_or_policy_limits": [],
            "attester_id": "owner_required",
            "attested_at": "YYYY-MM-DDTHH:MM:SSZ",
        },
    }


def attestation_template(kind: str, subject: str | None = None) -> dict[str, Any]:
    if kind not in {"profile", "path_purpose", "business_impact"}:
        raise ValueError("kind must be profile, path_purpose, or business_impact")
    common = {
        "schema_version": "1.0",
        "kind": kind,
        "subject": subject or "owner_required",
        "attester_id": "owner_required",
        "attester_role": "owner_required",
        "attested_at": "YYYY-MM-DDTHH:MM:SSZ",
        "confidence": "LOW | MEDIUM | HIGH",
        "evidence_source": "owner_required",
        "notes": "",
    }
    if kind == "profile":
        common["claims"] = {
            "profile_matches_target_platform": "true | false | unknown",
            "quota_or_policy_limits_included": "true | false | unknown",
            "offline_export_current_as_of": "YYYY-MM-DD",
        }
    elif kind == "path_purpose":
        common["claims"] = {
            "paths_are_application_owned": "true | false | unknown",
            "writer_topology_confirmed": "true | false | unknown",
            "shared_storage_dependency_confirmed": "true | false | unknown",
        }
    else:
        common["claims"] = {
            "assessment_minutes_supported": "true | false | unknown",
            "decision_supported_by_assessment": "true | false | unknown",
            "business_outcome_source": "owner_required",
        }
    return common


def _is_placeholder(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {"", "owner_required", "unknown", "yyyy-mm-dd", "yyyy-mm-ddthh:mm:ssz"} or "|" in text


def validate_attestation_data(data: dict[str, Any], expected_kind: str | None = None) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    if data.get("schema_version") != "1.0":
        issues.append("SCHEMA_VERSION_INVALID_OR_MISSING")
    kind = data.get("kind")
    if expected_kind and kind != expected_kind:
        issues.append("ATTESTATION_KIND_MISMATCH")
    if kind not in {"profile", "path_purpose", "business_impact"}:
        issues.append("ATTESTATION_KIND_INVALID")
    for field in ["subject", "attester_id", "attester_role", "attested_at", "confidence", "evidence_source"]:
        if _is_placeholder(data.get(field)):
            issues.append(f"ATTESTATION_FIELD_PLACEHOLDER:{field}")
    if str(data.get("confidence", "")).upper() not in {"LOW", "MEDIUM", "HIGH"}:
        issues.append("ATTESTATION_CONFIDENCE_INVALID")
    claims = data.get("claims")
    if not isinstance(claims, dict) or not claims:
        issues.append("ATTESTATION_CLAIMS_MISSING")
    else:
        for key, value in claims.items():
            if _is_placeholder(value):
                warnings.append(f"ATTESTATION_CLAIM_UNRESOLVED:{key}")
    return {
        "schema_version": "1.0",
        "valid": not issues,
        "kind": kind,
        "issues": issues,
        "warnings": warnings,
    }


def validate_attestation(path: Path, expected_kind: str | None = None) -> dict[str, Any]:
    data = _load_yaml(path)
    return validate_attestation_data(data, expected_kind=expected_kind)


def real_world_evidence_contract() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "purpose": "Required non-generated evidence before empirical calibration or measured business-impact claims.",
        "generated_data_boundary": {
            "generated_cases_may_support": ["parser coverage", "workflow regression", "reason-code regression"],
            "generated_cases_must_not_support": [
                "field accuracy claims",
                "measured operational impact",
                "production readiness",
                "customer or portfolio value claims",
            ],
        },
        "required_for_business_impact": [
            "non_generated_bundle",
            "profile_attestation",
            "path_purpose_attestation",
            "two_expert_reviews_or_adjudication",
            "decisive_outcome",
            "business_impact_record_with_source",
            "baseline_or_before_after_measurement",
        ],
        "required_for_calibration": [
            "non_generated_bundle",
            "trusted_label",
            "decisive_storage_relevant_outcome",
            "case_contract_valid",
            "policy_pack_version_when_used",
        ],
        "minimum_real_case_mix": {
            "failure_cases": ["no_rwx_profile", "raw_block_no_profile", "capacity_exceeds_profile", "no_storage_class_match"],
            "degraded_evidence_cases": ["missing_iostat", "missing_ps", "uncertain_mapping", "root_only"],
            "boundary_cases": ["medium_capacity", "medium_latency", "expansion_tie", "snapshot_tie"],
            "topology_cases": ["lvm", "multipath_or_device_mapper", "network_filesystem_variants", "multi_vm_shared_storage"],
        },
        "claim_rules": {
            "SIMULATED_ONLY": "Generated or synthetic records may demonstrate workflow coverage only.",
            "MEASURED_OPERATIONAL": "Requires at least one high-quality non-generated business-impact record.",
            "PRODUCTION_READY": "Requires corpus release gate with trusted non-generated cases and acceptable failure rates.",
        },
    }


def operating_model_template() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "roles": {
            "workload_owner": {
                "responsibilities": [
                    "attest path purpose and writer topology",
                    "identify collection window",
                    "confirm backup, restore, failover, and batch behavior",
                ],
                "required_artifacts": ["path_purpose_attestation", "owner_evidence"],
            },
            "storage_platform_owner": {
                "responsibilities": [
                    "attest storage profile currency",
                    "record quotas and policy limits",
                    "accept or reject capability-gap findings",
                ],
                "required_artifacts": ["profile_attestation", "profile_snapshot"],
            },
            "reviewer": {
                "responsibilities": [
                    "review PASS/REVIEW/FAIL decisions",
                    "record reason-code agreement or disagreement",
                    "escalate disagreements for adjudication",
                ],
                "required_artifacts": ["expert_review", "adjudication_when_needed"],
            },
            "outcome_owner": {
                "responsibilities": [
                    "record decisive outcome",
                    "record observed blockers",
                    "record operational business impact with source",
                ],
                "required_artifacts": ["outcome_record", "business_impact_record"],
            },
        },
        "workflow_states": [
            "bundle_collected",
            "owner_attested",
            "engine_analyzed",
            "expert_reviewed",
            "adjudicated_when_needed",
            "outcome_linked",
            "impact_recorded",
            "eligible_for_calibration",
        ],
        "sla_defaults": {
            "expert_review_due_days": 7,
            "outcome_due_days": 30,
            "impact_due_days": 30,
        },
        "gate_policy": {
            "business_review": "May proceed only with valid input and decision artifacts; generated-only impact claims stay simulated.",
            "calibration": "Requires trusted non-generated labels and decisive outcomes.",
            "release": "Requires production-ready corpus evaluation.",
        },
    }


def timestamp_attestation_template() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "purpose": "Optional external timestamp or evidence repository reference for regulated handoff.",
        "audit_fingerprint": "sha256_required",
        "external_timestamp_reference": "owner_required",
        "timestamp_provider_or_repository": "owner_required",
        "recorded_at": "YYYY-MM-DDTHH:MM:SSZ",
        "attester_id": "owner_required",
        "notes": "",
    }


def evidence_repository_export(audit_dir: Path) -> dict[str, Any]:
    manifest = audit_manifest(audit_dir)
    return {
        "schema_version": "1.0",
        "created_at": now_utc(),
        "source_audit_dir": str(audit_dir),
        "audit_fingerprint": manifest["audit_fingerprint"],
        "repository_contract": {
            "mode": "offline_export",
            "network_calls_performed": False,
            "required_repository_fields": [
                "workload_id",
                "evidence_bundle_fingerprint",
                "profile_fingerprint",
                "attestation_status",
                "review_status",
                "outcome_status",
                "impact_status",
                "access_control_owner",
            ],
        },
        "files": manifest["files"],
    }


def chain_of_custody_record(
    audit_dir: Path,
    *,
    external_timestamp_reference: str | None = None,
    signer_id: str | None = None,
) -> dict[str, Any]:
    manifest = audit_manifest(audit_dir)
    warnings: list[str] = []
    if not external_timestamp_reference:
        warnings.append("EXTERNAL_TIMESTAMP_REFERENCE_MISSING")
    if not signer_id:
        warnings.append("SIGNER_ID_NOT_SUPPLIED")
    return {
        "schema_version": "1.0",
        "created_at": now_utc(),
        "audit_dir": str(audit_dir),
        "audit_fingerprint": manifest["audit_fingerprint"],
        "file_count": manifest["file_count"],
        "signer_id": signer_id,
        "external_timestamp_reference": external_timestamp_reference,
        "tamper_evidence": manifest["tamper_evidence"],
        "warnings": warnings,
    }


def sign_audit_manifest(manifest_path: Path, key_file: Path) -> dict[str, Any]:
    manifest_bytes = manifest_path.read_bytes()
    key = key_file.read_bytes().strip()
    digest = hmac.new(key, manifest_bytes, hashlib.sha256).hexdigest()
    return {
        "schema_version": "1.0",
        "created_at": now_utc(),
        "algorithm": "HMAC-SHA256",
        "manifest": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "signature": digest,
        "key_id": hashlib.sha256(key).hexdigest()[:16],
        "warning": "HMAC proves possession of the shared key; it is not a public-key non-repudiation signature.",
    }


def verify_audit_manifest_signature(signature_path: Path, key_file: Path) -> dict[str, Any]:
    signature = _load_json(signature_path)
    expected = sign_audit_manifest(Path(signature["manifest"]), key_file)
    return {
        "schema_version": "1.0",
        "valid": hmac.compare_digest(str(signature.get("signature")), expected["signature"]),
        "algorithm": signature.get("algorithm"),
        "manifest": signature.get("manifest"),
        "issues": [] if hmac.compare_digest(str(signature.get("signature")), expected["signature"]) else ["SIGNATURE_MISMATCH"],
    }


def trend_report(decisions: list[Path]) -> dict[str, Any]:
    rows = []
    for index, path in enumerate(decisions):
        data = _load_json(path)
        rows.append(
            {
                "sequence": index + 1,
                "path": str(path),
                "fit_status": data.get("fit_status"),
                "recommended_storage_class": data.get("recommended_storage_class"),
                "storage_request_gib": data.get("storage_request_gib"),
                "capacity_risk": data.get("capacity_risk"),
                "latency_risk": data.get("latency_risk"),
                "confidence": data.get("confidence"),
                "warnings": data.get("warnings", []),
                "blockers": data.get("blockers", []),
            }
        )
    transitions = []
    for previous, current in zip(rows, rows[1:]):
        changed = {
            field: {"from": previous.get(field), "to": current.get(field)}
            for field in ["fit_status", "capacity_risk", "latency_risk", "confidence", "storage_request_gib"]
            if previous.get(field) != current.get(field)
        }
        transitions.append({"from": previous["path"], "to": current["path"], "changed_fields": changed})
    return {
        "schema_version": "1.0",
        "decision_count": len(rows),
        "rows": rows,
        "transitions": transitions,
        "trend_flags": [
            "CAPACITY_REQUEST_INCREASED"
            for previous, current in zip(rows, rows[1:])
            if (current.get("storage_request_gib") or 0) > (previous.get("storage_request_gib") or 0)
        ],
    }


def followup_sla(corpus_dir: Path, *, review_due_days: int = 7, outcome_due_days: int = 30) -> dict[str, Any]:
    items = []
    for path in sorted(corpus_dir.glob("*.yml")):
        case = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        validation = validate_case(path)
        if not validation.get("trusted_label"):
            items.append(
                {
                    "case_id": case.get("id") or path.stem,
                    "followup_type": "expert_review_or_adjudication",
                    "priority": "HIGH",
                    "due_in_days": review_due_days,
                    "reason": "Case is not trusted-label ready.",
                }
            )
        elif validation.get("decisive_outcome_count", 0) == 0:
            items.append(
                {
                    "case_id": case.get("id") or path.stem,
                    "followup_type": "decisive_outcome",
                    "priority": "HIGH",
                    "due_in_days": outcome_due_days,
                    "reason": "Trusted-label case lacks decisive outcome.",
                }
            )
        if validation.get("business_impact_quality_score", 0) < 70:
            items.append(
                {
                    "case_id": case.get("id") or path.stem,
                    "followup_type": "business_impact",
                    "priority": "MEDIUM",
                    "due_in_days": outcome_due_days,
                    "reason": "Business impact record is absent or low quality.",
                }
            )
    return {
        "schema_version": "1.0",
        "corpus_dir": str(corpus_dir),
        "review_due_days": review_due_days,
        "outcome_due_days": outcome_due_days,
        "item_count": len(items),
        "items": items,
    }


def handoff_bundle(audit_dir: Path, output: Path) -> dict[str, Any]:
    manifest = audit_manifest(audit_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("audit-manifest.generated.json", json.dumps(manifest, indent=2) + "\n")
        for path in sorted(audit_dir.rglob("*")):
            if path.is_file() and path.resolve() != output.resolve():
                archive.write(path, path.relative_to(audit_dir))
    return {
        "schema_version": "1.0",
        "audit_dir": str(audit_dir),
        "output": str(output),
        "file_count": manifest["file_count"],
        "audit_fingerprint": manifest["audit_fingerprint"],
        "note": "ZIP packaging is local-only and contains the files already present in the audit directory.",
    }
