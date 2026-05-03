from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .corpus import STORAGE_FAILURE_OUTCOMES, SUCCESS_OUTCOMES, evaluate_corpus
from .engine import analyze_paths
from .models import model_to_dict
from .origins import is_generated_origin
from .storage_profile import parse_storage_profile_file, profile_fingerprint


CORE_BUNDLE_FILES = {
    "df": "df.txt",
    "mount": "mount.txt",
    "fstab": "fstab.txt",
    "iostat": "iostat.txt",
    "ps": "ps.txt",
}

OPTIONAL_BUNDLE_FILES = {
    "findmnt_json": "findmnt.json",
    "lsblk_json": "lsblk.json",
    "blkid": "blkid.txt",
    "pvs": "pvs.txt",
    "vgs": "vgs.txt",
    "lvs": "lvs.txt",
    "inode_df": "inode-df.txt",
    "path_purpose": "path-purpose.yml",
    "redaction_map": "redaction-map.json",
    "redaction_map_du": "redaction-map-du.json",
}

VALID_FIT_STATUSES = {"PASS", "REVIEW", "FAIL"}
VALID_OUTCOME_STATUSES = SUCCESS_OUTCOMES | STORAGE_FAILURE_OUTCOMES | {
    "blocked_by_non_storage",
    "not_attempted",
    "unknown",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(root)),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def bundle_paths(bundle_dir: Path) -> dict[str, Path | None]:
    paths: dict[str, Path | None] = {}
    for key, filename in {**CORE_BUNDLE_FILES, **OPTIONAL_BUNDLE_FILES}.items():
        path = bundle_dir / filename
        paths[key] = path if path.exists() else None
    du_summary = bundle_dir / "du-summary.txt"
    paths["du_summary"] = du_summary if du_summary.exists() else None
    return paths


def validate_bundle(bundle_dir: Path) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    manifest_path = bundle_dir / "manifest.json"
    if not bundle_dir.exists() or not bundle_dir.is_dir():
        return {
            "valid": False,
            "issues": ["BUNDLE_DIRECTORY_MISSING"],
            "warnings": [],
            "overall_bundle_quality_score": 0.0,
            "bundle_quality_score": 0.0,
            "core_file_status": {},
            "optional_file_status": {},
        }
    if not manifest_path.exists():
        issues.append("MANIFEST_MISSING")
        manifest: dict[str, Any] = {}
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return {
                "valid": False,
                "issues": [f"MANIFEST_INVALID_JSON:{exc}"],
                "warnings": [],
                "overall_bundle_quality_score": 0.0,
                "bundle_quality_score": 0.0,
                "core_file_status": {},
                "optional_file_status": {},
            }

    files_by_path = {item.get("path"): item for item in manifest.get("files", []) if isinstance(item, dict)}
    core_status: dict[str, str] = {}
    optional_status: dict[str, str] = {}

    command_by_file = {
        command.get("file"): command for command in manifest.get("commands", []) if isinstance(command, dict)
    }
    collection_issue_codes: list[str] = []

    def check_file(filename: str, required: bool) -> str:
        path = bundle_dir / filename
        command = command_by_file.get(filename, {})
        command_status = command.get("status")
        if command_status in {"command_failed", "command_not_found", "timeout"}:
            collection_issue_codes.append(f"{command_status.upper()}:{filename}")
        if not path.exists():
            if required:
                issues.append(f"CORE_FILE_MISSING:{filename}")
            return "missing"
        if path.stat().st_size == 0:
            warnings.append(f"FILE_EMPTY:{filename}")
            if not required:
                collection_issue_codes.append(f"EMPTY_OPTIONAL_TOPOLOGY_OUTPUT:{filename}")
            return "empty"
        record = files_by_path.get(filename)
        if record and record.get("sha256") and record["sha256"] != sha256_file(path):
            issues.append(f"CHECKSUM_MISMATCH:{filename}")
            return "checksum_mismatch"
        return "present"

    for _, filename in CORE_BUNDLE_FILES.items():
        core_status[filename] = check_file(filename, required=True)
    for _, filename in OPTIONAL_BUNDLE_FILES.items():
        optional_status[filename] = check_file(filename, required=False)

    non_topology_optional = {"redaction-map.json", "redaction-map-du.json", "path-purpose.yml"}
    topology_status = {
        filename: status for filename, status in optional_status.items() if filename not in non_topology_optional
    }
    present_core = sum(1 for status in core_status.values() if status == "present")
    present_topology = sum(1 for status in topology_status.values() if status == "present")
    core_score = present_core / len(CORE_BUNDLE_FILES)
    topology_score = present_topology / len(topology_status) if topology_status else 0.0
    ps_status = core_status.get("ps.txt")
    app_score = 0.5 if ps_status == "present" else 0.0
    redaction_mode = str(manifest.get("redaction_mode", "unknown"))
    redaction_map_status = optional_status.get("redaction-map.json", "missing")
    redaction_score = 1.0
    if redaction_mode.startswith("redact_first"):
        redaction_score = 1.0 if redaction_map_status == "present" else 0.4
    quality = round((core_score * 0.55) + (topology_score * 0.2) + (app_score * 0.15) + (redaction_score * 0.1), 3)
    command_status_counts: dict[str, int] = {}
    for command in manifest.get("commands", []):
        status = str(command.get("status", "unknown"))
        command_status_counts[status] = command_status_counts.get(status, 0) + 1

    return {
        "valid": not issues,
        "schema_version": manifest.get("schema_version"),
        "collector_version": manifest.get("collector_version"),
        "bundle_fingerprint": manifest.get("bundle_fingerprint"),
        "redaction_mode": redaction_mode,
        "issues": issues,
        "warnings": warnings,
        "collection_issue_codes": sorted(set(collection_issue_codes)),
        "core_completeness_score": round(core_score, 3),
        "topology_completeness_score": round(topology_score, 3),
        "application_evidence_score": round(app_score, 3),
        "redaction_preservation_score": round(redaction_score, 3),
        "overall_bundle_quality_score": quality,
        "bundle_quality_score": quality,
        "core_file_status": core_status,
        "optional_file_status": optional_status,
        "command_status_counts": command_status_counts,
    }


def build_manifest(
    bundle_dir: Path,
    *,
    commands: list[dict[str, Any]],
    collector_version: str,
    redaction_mode: str,
    safe_host_facts: dict[str, Any],
) -> dict[str, Any]:
    files = [
        file_record(path, bundle_dir)
        for path in sorted(bundle_dir.iterdir())
        if path.is_file() and path.name != "manifest.json"
    ]
    fingerprint_source = "\n".join(f"{item['path']}:{item['sha256']}" for item in files)
    return {
        "schema_version": "1.0",
        "collector_version": collector_version,
        "collected_at": now_utc(),
        "redaction_mode": redaction_mode,
        "safe_host_facts": safe_host_facts,
        "commands": commands,
        "files": files,
        "bundle_fingerprint": hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest(),
    }


def storage_profile_snapshot(
    storage_profile_path: Path,
    *,
    origin: str = "user_supplied",
    owner_note: str | None = None,
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = parse_storage_profile_file(storage_profile_path)
    return {
        "schema_version": "1.0",
        "path": str(storage_profile_path),
        "sha256": sha256_file(storage_profile_path),
        "captured_at": now_utc(),
        "fingerprint": profile_fingerprint(profile),
        "origin": origin,
        "owner_note": owner_note,
        "source_metadata": source_metadata or {},
        "storage_classes": [
            {
                "name": item.name,
                "access_modes": item.access_modes,
                "volume_modes": item.volume_modes,
                "storage_kind": item.storage_kind,
                "performance_tier": item.performance_tier,
                "max_size_gib": item.max_size_gib,
                "supports_expansion": item.supports_expansion,
                "supports_snapshots": item.supports_snapshots,
            }
            for item in profile.storage_classes
        ],
    }


def decision_record(result: Any) -> dict[str, Any]:
    data = model_to_dict(result)
    return {
        "schema_version": "1.0",
        "captured_at": now_utc(),
        "fit_status": data.get("fit_status"),
        "recommended_storage_class": data.get("recommended_storage_class"),
        "required_access_mode": data.get("required_access_mode"),
        "required_volume_mode": data.get("required_volume_mode"),
        "preferred_storage_kind": data.get("preferred_storage_kind"),
        "storage_request_gib": data.get("storage_request_gib"),
        "capacity_risk": data.get("capacity_risk"),
        "latency_risk": data.get("latency_risk"),
        "confidence": data.get("confidence"),
        "blockers": data.get("blockers", []),
        "warnings": data.get("warnings", []),
        "reason_codes": data.get("reason_codes", []),
        "evidence": data.get("evidence", {}),
        "analysis": data.get("analysis"),
    }


def _relative_or_absolute(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path.resolve())


def create_case_from_bundle(
    *,
    case_id: str,
    bundle_dir: Path,
    storage_profile_path: Path,
    output_path: Path,
    policy_pack_path: Path | None = None,
    config_path: Path | None = None,
    data_paths: list[str] | None = None,
    calibration_path: Path | None = None,
    app_metadata: dict[str, Any] | None = None,
    data_origin: str = "real_workload",
    profile_origin: str = "user_supplied",
) -> dict[str, Any]:
    paths = bundle_paths(bundle_dir)
    bundle_validation = validate_bundle(bundle_dir)
    from .calibration import load_calibration_report
    from .parse_extra import load_extra_evidence

    extra_evidence, _ = load_extra_evidence(
        findmnt_json=paths["findmnt_json"],
        lsblk_json=paths["lsblk_json"],
        blkid=paths["blkid"],
        pvs=paths["pvs"],
        vgs=paths["vgs"],
        lvs=paths["lvs"],
        inode_df=paths["inode_df"],
        du_summary=paths["du_summary"],
    )
    extra_evidence["bundle_validation"] = bundle_validation

    analysis = analyze_paths(
        df=paths["df"],
        mount=paths["mount"],
        fstab=paths["fstab"],
        iostat=paths["iostat"],
        ps=paths["ps"],
        storage_profile_path=storage_profile_path,
        config=config_path,
        policy_pack_path=policy_pack_path,
        data_paths=data_paths or [],
        strict=False,
        calibration_report=load_calibration_report(calibration_path),
        app_metadata=app_metadata,
        extra_evidence=extra_evidence,
    )
    case = {
        "schema_version": "1.0",
        "id": case_id,
        "case_kind": "created",
        "data_origin": data_origin,
        "profile_origin": profile_origin,
        "lifecycle_state": "engine_analyzed",
        "created_at": now_utc(),
        "bundle": {
            "path": str(bundle_dir.resolve()),
            "manifest": str((bundle_dir / "manifest.json").resolve()),
            "validation": bundle_validation,
        },
        "df": str(paths["df"].resolve()) if paths["df"] else None,
        "mount": str(paths["mount"].resolve()) if paths["mount"] else None,
        "fstab": str(paths["fstab"].resolve()) if paths["fstab"] else None,
        "iostat": str(paths["iostat"].resolve()) if paths["iostat"] else None,
        "ps": str(paths["ps"].resolve()) if paths["ps"] else None,
        "storage_profile": str(storage_profile_path.resolve()),
        "storage_profile_snapshot": storage_profile_snapshot(storage_profile_path, origin=profile_origin),
        "policy_pack": str(policy_pack_path.resolve()) if policy_pack_path else None,
        "config": str(config_path.resolve()) if config_path else None,
        "data_paths": data_paths or [],
        "app_metadata": app_metadata or {},
        "engine_decision": decision_record(analysis.result),
        "expert_reviews": [],
        "adjudication": None,
        "outcomes": [],
        "business_impact": [],
        "reviewer_notes": "Fill expert_reviews, adjudication, outcomes, and business_impact before relying on calibration.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")
    return case


def load_case(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("case file must contain a YAML mapping")
    return data


def save_case(path: Path, case: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")


def _review_decisions(case: dict[str, Any]) -> list[str]:
    return [
        str(review.get("fit_status"))
        for review in case.get("expert_reviews", [])
        if isinstance(review, dict) and review.get("fit_status")
    ]


def _consensus(values: list[str]) -> str | None:
    if not values:
        return None
    return values[0] if all(value == values[0] for value in values) else None


def validate_case(case_path: Path) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    case = load_case(case_path)
    for field in ["id", "data_origin", "profile_origin", "storage_profile", "engine_decision"]:
        if not case.get(field):
            issues.append(f"FIELD_MISSING:{field}")
    if case.get("engine_decision", {}).get("fit_status") not in VALID_FIT_STATUSES:
        issues.append("ENGINE_DECISION_INVALID_OR_MISSING_FIT_STATUS")

    bundle = case.get("bundle") or {}
    bundle_path = Path(bundle.get("path")) if bundle.get("path") else None
    bundle_validation = None
    if bundle_path:
        bundle_validation = validate_bundle(bundle_path)
        if not bundle_validation["valid"]:
            warnings.append("BUNDLE_VALIDATION_HAS_ISSUES")

    review_quality_scores = []
    for review in case.get("expert_reviews", []) or []:
        score = 0
        if review.get("fit_status") not in VALID_FIT_STATUSES:
            issues.append("EXPERT_REVIEW_INVALID_FIT_STATUS")
        if not review.get("reviewer_id"):
            warnings.append("EXPERT_REVIEW_MISSING_REVIEWER_ID")
        else:
            score += 20
        for field in ["fit_status", "required_access_mode", "required_volume_mode", "preferred_storage_kind", "confidence"]:
            if review.get(field):
                score += 10
            else:
                warnings.append(f"EXPERT_REVIEW_MISSING_{field.upper()}")
        if "reason_code_agreement" in review or "reason_code_disagreement" in review:
            score += 20
        else:
            warnings.append("EXPERT_REVIEW_MISSING_REASON_CODE_AGREEMENT")
        review_quality_scores.append(min(score, 100))
    outcome_quality_scores = []
    for outcome in case.get("outcomes", []) or []:
        score = 0
        if outcome.get("status") not in VALID_OUTCOME_STATUSES:
            issues.append(f"OUTCOME_INVALID_STATUS:{outcome.get('status')}")
        else:
            score += 25
        for field in ["recorded_at", "source_team", "confidence"]:
            if outcome.get(field):
                score += 15
            else:
                warnings.append(f"OUTCOME_MISSING_{field.upper()}")
        if outcome.get("target_storage_class") or outcome.get("final_storage_pattern"):
            score += 15
        if outcome.get("observed_storage_blockers") is not None:
            score += 15
        outcome_quality_scores.append(min(score, 100))
    impact_quality_scores = []
    for impact in case.get("business_impact", []) or []:
        score = 0
        for field in ["recorded_at", "decision", "confidence", "source"]:
            if impact.get(field):
                score += 15
            else:
                warnings.append(f"IMPACT_MISSING_{field.upper()}")
        for field in ["assessment_minutes", "expert_review_minutes"]:
            if impact.get(field) is not None:
                score += 10
        for field in ["blocker_found_before_pilot", "failed_pilot_avoided", "platform_gap_identified"]:
            if impact.get(field) is not None:
                score += 5
        impact_quality_scores.append(min(score, 100))
    consensus = _consensus(_review_decisions(case))
    decisive_outcomes = [
        outcome
        for outcome in case.get("outcomes", []) or []
        if outcome.get("status") in SUCCESS_OUTCOMES or outcome.get("status") in STORAGE_FAILURE_OUTCOMES
    ]
    review_count = len(case.get("expert_reviews", []) or [])
    review_quality_score = round(sum(review_quality_scores) / len(review_quality_scores), 3) if review_quality_scores else 0.0
    outcome_quality_score = round(sum(outcome_quality_scores) / len(outcome_quality_scores), 3) if outcome_quality_scores else 0.0
    impact_quality_score = round(sum(impact_quality_scores) / len(impact_quality_scores), 3) if impact_quality_scores else 0.0
    has_adjudication = bool(case.get("adjudication"))
    data_origin = str(case.get("data_origin", "unknown"))
    synthetic_origin = is_generated_origin(data_origin) or case.get("case_kind") == "synthetic" or case.get("label_source") == "synthetic"
    trusted_label = has_adjudication or (review_count >= 2 and consensus is not None and review_quality_score >= 70)
    if synthetic_origin and trusted_label:
        warnings.append("SYNTHETIC_CASE_EXCLUDED_FROM_CALIBRATION_READINESS")
        trusted_label = False
    if review_count == 1 and not has_adjudication:
        warnings.append("ONLY_ONE_EXPERT_REVIEW")
    if review_count >= 2 and consensus is None and not has_adjudication:
        issues.append("REVIEW_DISAGREEMENT_REQUIRES_ADJUDICATION")
    calibration_ready = trusted_label and bool(decisive_outcomes) and outcome_quality_score >= 70
    return {
        "schema_version": "1.0",
        "valid": not issues,
        "case_id": case.get("id"),
        "lifecycle_state": case.get("lifecycle_state", "unknown"),
        "issues": issues,
        "warnings": warnings,
        "trusted_label": trusted_label,
        "expert_review_count": review_count,
        "expert_consensus": consensus,
        "review_quality_score": review_quality_score,
        "decisive_outcome_count": len(decisive_outcomes),
        "outcome_quality_score": outcome_quality_score,
        "business_impact_quality_score": impact_quality_score,
        "calibration_ready": calibration_ready,
        "bundle_validation": bundle_validation,
    }


def add_review(case_path: Path, review_path: Path) -> dict[str, Any]:
    case = load_case(case_path)
    review = yaml.safe_load(review_path.read_text(encoding="utf-8")) or {}
    if not isinstance(review, dict):
        raise ValueError("review file must contain a YAML mapping")
    if review.get("fit_status") not in VALID_FIT_STATUSES:
        raise ValueError("review.fit_status must be PASS, REVIEW, or FAIL")
    review.setdefault("reviewed_at", now_utc())
    case.setdefault("expert_reviews", []).append(review)
    consensus = _consensus(_review_decisions(case))
    if len(case["expert_reviews"]) >= 2:
        case["lifecycle_state"] = "expert_reviewed" if consensus else "needs_adjudication"
    else:
        case["lifecycle_state"] = "review_in_progress"
    save_case(case_path, case)
    return case


def adjudicate_case(case_path: Path, adjudication_path: Path | None = None) -> dict[str, Any]:
    case = load_case(case_path)
    if adjudication_path is not None:
        adjudication = yaml.safe_load(adjudication_path.read_text(encoding="utf-8")) or {}
        if not isinstance(adjudication, dict):
            raise ValueError("adjudication file must contain a YAML mapping")
    else:
        consensus = _consensus(_review_decisions(case))
        if not consensus:
            raise ValueError("adjudication file is required when expert reviews do not agree")
        adjudication = {
            "adjudicator_id": "consensus",
            "adjudicated_at": now_utc(),
            "fit_status": consensus,
            "rationale": "Expert reviews reached consensus.",
        }
    if adjudication.get("fit_status") not in VALID_FIT_STATUSES:
        raise ValueError("adjudication.fit_status must be PASS, REVIEW, or FAIL")
    adjudication.setdefault("adjudicated_at", now_utc())
    case["adjudication"] = adjudication
    case["adjudicated_fit_status"] = adjudication["fit_status"]
    for field in ["required_access_mode", "required_volume_mode", "preferred_storage_kind"]:
        if adjudication.get(field):
            case.setdefault("expected_requirements", {})[field] = adjudication[field]
    case["lifecycle_state"] = "adjudicated"
    save_case(case_path, case)
    return case


def add_outcome(case_path: Path, outcome_path: Path | None = None, *, status: str | None = None, notes: str | None = None) -> dict[str, Any]:
    case = load_case(case_path)
    if outcome_path is not None:
        outcome = yaml.safe_load(outcome_path.read_text(encoding="utf-8")) or {}
        if not isinstance(outcome, dict):
            raise ValueError("outcome file must contain a YAML mapping")
    else:
        if status is None:
            raise ValueError("--status or --outcome is required")
        outcome = {"status": status, "notes": notes or "", "source_team": "unspecified", "confidence": "LOW"}
    if outcome.get("status") not in VALID_OUTCOME_STATUSES:
        raise ValueError(f"outcome.status must be one of: {', '.join(sorted(VALID_OUTCOME_STATUSES))}")
    outcome.setdefault("recorded_at", now_utc())
    case.setdefault("outcomes", []).append(outcome)
    if outcome["status"] in SUCCESS_OUTCOMES or outcome["status"] in STORAGE_FAILURE_OUTCOMES:
        case["lifecycle_state"] = "outcome_linked"
    elif case.get("lifecycle_state") not in {"outcome_linked", "retired"}:
        case["lifecycle_state"] = "awaiting_outcome"
    save_case(case_path, case)
    return case


def add_impact(case_path: Path, impact_path: Path | None = None, **fields) -> dict[str, Any]:
    case = load_case(case_path)
    if impact_path is not None:
        impact = yaml.safe_load(impact_path.read_text(encoding="utf-8")) or {}
        if not isinstance(impact, dict):
            raise ValueError("impact file must contain a YAML mapping")
    else:
        impact = {key: value for key, value in fields.items() if value is not None}
    impact.setdefault("recorded_at", now_utc())
    impact.setdefault("source", "unspecified")
    impact.setdefault("confidence", "LOW")
    case.setdefault("business_impact", []).append(impact)
    save_case(case_path, case)
    return case


def corpus_summary(corpus_dir: Path) -> dict[str, Any]:
    cases = []
    lifecycle_counts: dict[str, int] = {}
    calibration_ready = 0
    outcome_backlog = []
    for path in sorted(corpus_dir.glob("*.yml")):
        validation = validate_case(path)
        state = validation["lifecycle_state"]
        lifecycle_counts[state] = lifecycle_counts.get(state, 0) + 1
        if validation["calibration_ready"]:
            calibration_ready += 1
        elif validation["trusted_label"] and validation["decisive_outcome_count"] == 0:
            outcome_backlog.append(validation["case_id"])
        cases.append(validation)
    evaluation = evaluate_corpus(corpus_dir) if cases else None
    return {
        "schema_version": "1.0",
        "case_count": len(cases),
        "lifecycle_counts": dict(sorted(lifecycle_counts.items())),
        "calibration_ready_count": calibration_ready,
        "outcome_backlog": outcome_backlog,
        "readiness": evaluation.get("readiness") if evaluation else None,
        "cases": cases,
    }


def outcome_backlog(corpus_dir: Path) -> dict[str, Any]:
    summary = corpus_summary(corpus_dir)
    backlog = [
        case for case in summary["cases"] if case["trusted_label"] and case["decisive_outcome_count"] == 0
    ]
    return {"schema_version": "1.0", "count": len(backlog), "cases": backlog}


def export_outcome_requests(corpus_dir: Path) -> dict[str, Any]:
    backlog = outcome_backlog(corpus_dir)
    return {
        "schema_version": "1.0",
        "requests": [
            {
                "case_id": item["case_id"],
                "requested_fields": [
                    "status",
                    "recorded_at",
                    "source_team",
                    "confidence",
                    "target_storage_class",
                    "final_storage_pattern",
                    "observed_storage_blockers",
                    "notes",
                ],
            }
            for item in backlog["cases"]
        ],
    }


def corpus_coverage(corpus_dir: Path) -> dict[str, Any]:
    coverage_targets = {
        "relational_database": 25,
        "shared_filesystem": 25,
        "file_server": 15,
        "search_logging": 15,
        "queue_streaming": 10,
        "generic_stateful_app": 10,
    }
    reason_targets = {
        "CAPACITY_RISK_HIGH": 10,
        "LATENCY_RISK_HIGH": 10,
        "RAW_BLOCK_HINT": 5,
        "SHARED_FS_DETECTED": 25,
    }
    family_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    outcome_counts: dict[str, int] = {}
    capability_counts: dict[str, int] = {}
    for path in sorted(corpus_dir.glob("*.yml")):
        case = load_case(path)
        family = (case.get("app_metadata") or {}).get("workload_family") or case.get("workload_family") or case.get("labels", {}).get("workload_family") or "unknown"
        family_counts[family] = family_counts.get(family, 0) + 1
        decision = case.get("engine_decision") or {}
        for code in decision.get("reason_codes", []) or []:
            reason_counts[code] = reason_counts.get(code, 0) + 1
        if decision.get("required_access_mode") == "ReadWriteMany":
            capability_counts["rwx"] = capability_counts.get("rwx", 0) + 1
        if decision.get("preferred_storage_kind") == "block":
            capability_counts["block"] = capability_counts.get("block", 0) + 1
        if "FAST_STORAGE_RECOMMENDED" in (decision.get("reason_codes") or []):
            capability_counts["fast_block"] = capability_counts.get("fast_block", 0) + 1
        for outcome in case.get("outcomes", []) or []:
            status = outcome.get("status", "unknown")
            outcome_counts[status] = outcome_counts.get(status, 0) + 1
    family_gaps = {
        name: max(target - family_counts.get(name, 0), 0) for name, target in coverage_targets.items()
    }
    reason_gaps = {
        name: max(target - reason_counts.get(name, 0), 0) for name, target in reason_targets.items()
    }
    return {
        "schema_version": "1.0",
        "family_counts": dict(sorted(family_counts.items())),
        "reason_code_counts": dict(sorted(reason_counts.items())),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "capability_counts": dict(sorted(capability_counts.items())),
        "family_coverage_gaps": family_gaps,
        "reason_coverage_gaps": reason_gaps,
    }


def compare_evaluations(old_path: Path, new_path: Path) -> dict[str, Any]:
    old = json.loads(old_path.read_text(encoding="utf-8"))
    new = json.loads(new_path.read_text(encoding="utf-8"))

    def pass_failure(report):
        return (
            report.get("outcome_metrics", {})
            .get("by_predicted_status", {})
            .get("PASS", {})
            .get("storage_failure_rate")
        )

    old_pf = pass_failure(old)
    new_pf = pass_failure(new)
    regressions: list[str] = []
    if old_pf is not None and new_pf is not None and new_pf > old_pf:
        regressions.append("PASS_STORAGE_FAILURE_RATE_REGRESSION")
    old_acc = old.get("decision_accuracy")
    new_acc = new.get("decision_accuracy")
    if old_acc is not None and new_acc is not None and new_acc < old_acc:
        regressions.append("DECISION_ACCURACY_REGRESSION")
    return {
        "schema_version": "1.0",
        "old_readiness": (old.get("readiness") or {}).get("level"),
        "new_readiness": (new.get("readiness") or {}).get("level"),
        "old_decision_accuracy": old_acc,
        "new_decision_accuracy": new_acc,
        "old_pass_storage_failure_rate": old_pf,
        "new_pass_storage_failure_rate": new_pf,
        "regressions": regressions,
        "release_gate_passed": not regressions,
    }
