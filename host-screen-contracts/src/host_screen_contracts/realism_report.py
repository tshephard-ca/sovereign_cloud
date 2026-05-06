from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .benchmark import benchmark_dataset_package
from .dataset_model import DatasetManifest, manifest_cases, load_dataset_manifest
from .dataset_validate import validate_dataset_package


MATURITY_EVIDENCE = {
    "L0": "synthetic_demo",
    "L1": "domain_realistic_synthetic",
    "L2": "sanitized_non_production_capture",
    "L3": "real_structure_with_fake_or_tokenized_values",
    "L4": "real_multi_case_package",
    "L5": "real_drift_package",
    "L6": "portfolio_metrics_only",
}
EVIDENCE_KIND_LABELS = {
    "deterministic_synthetic": "deterministic_synthetic",
    "domain_realistic_synthetic": "domain_realistic_synthetic",
    "sanitized_local_capture": "sanitized_local_capture",
    "real_structure_tokenized": "real_structure_with_fake_or_tokenized_values",
    "real_multi_case": "real_multi_case_package",
    "real_drift": "real_drift_package",
    "portfolio_metrics": "portfolio_metrics_only",
}

BUSINESS_PATH_TAGS = {"inquiry", "update", "selection", "confirmation"}
NEGATIVE_PATH_TAGS = {"error_path", "not_found", "validation_error", "permission_denied", "cancel_fkey"}
CHANGE_RISK_TAGS = {"label_drift", "field_move_drift", "attribute_drift", "volatile_region"}
DATA_RISK_TAGS = {"sensitive", "hidden_field", "plain_text_only", "subfile", "paging"}


def _load_provenance(root: Path) -> dict[str, Any]:
    provenance_path = root / "provenance" / "generation.yml"
    if not provenance_path.exists():
        return {}
    return yaml.safe_load(provenance_path.read_text()) or {}


def _score_manifest(manifest: DatasetManifest, validation: dict[str, Any], benchmark: dict[str, Any]) -> tuple[int, list[str], list[str], dict[str, int]]:
    tags = set(manifest.tags)
    score = 0
    strengths: list[str] = []
    gaps: list[str] = []

    maturity_points = {"L0": 5, "L1": 15, "L2": 30, "L3": 45, "L4": 60, "L5": 70, "L6": 55}
    scored_maturity = manifest.simulates_maturity_level or manifest.maturity_level
    dimensions: dict[str, int] = {}
    dimensions["evidence_shape"] = maturity_points.get(scored_maturity, 0)
    score += dimensions["evidence_shape"]
    evidence_label = EVIDENCE_KIND_LABELS.get(manifest.evidence_kind or "", MATURITY_EVIDENCE.get(manifest.maturity_level, "unknown"))
    strengths.append(f"evidence_level:{evidence_label}")

    if validation.get("ok"):
        dimensions["package_validity"] = 10
        score += dimensions["package_validity"]
        strengths.append("package_validates")
    else:
        dimensions["package_validity"] = 0
        gaps.append("package_has_blockers")

    ready_rate = float(benchmark.get("contract_ready_rate", 0))
    dimensions["contract_readiness"] = round(ready_rate * 10)
    score += dimensions["contract_readiness"]
    if ready_rate:
        strengths.append("has_contract_ready_cases")
    else:
        gaps.append("no_high_confidence_contract_ready_case")

    field_map_coverage = float(benchmark.get("field_map_coverage", 0))
    dimensions["field_map_coverage"] = round(min(field_map_coverage, 1.0) * 8)
    score += dimensions["field_map_coverage"]
    if field_map_coverage >= 0.8:
        strengths.append("field_map_covers_extracted_fields")
    else:
        gaps.append("field_map_coverage_below_80_percent")

    if tags.intersection(BUSINESS_PATH_TAGS):
        dimensions["business_path"] = 4
        score += dimensions["business_path"]
        strengths.append("business_path_present")
    else:
        dimensions["business_path"] = 0
        gaps.append("missing_business_path_tag")

    if tags.intersection(NEGATIVE_PATH_TAGS):
        dimensions["negative_path"] = 4
        score += dimensions["negative_path"]
        strengths.append("negative_path_present")
    else:
        dimensions["negative_path"] = 0
        gaps.append("missing_negative_path")

    if tags.intersection(CHANGE_RISK_TAGS):
        dimensions["change_or_drift_signal"] = 4
        score += dimensions["change_or_drift_signal"]
        strengths.append("change_or_drift_signal_present")
    else:
        dimensions["change_or_drift_signal"] = 0
        gaps.append("missing_drift_or_change_signal")

    if tags.intersection(DATA_RISK_TAGS):
        dimensions["data_risk_scenario"] = 3
        score += dimensions["data_risk_scenario"]
        strengths.append("data_risk_scenario_present")
    else:
        dimensions["data_risk_scenario"] = 0
        gaps.append("missing_sensitive_or_complex_screen_scenario")

    if manifest.business_process and manifest.operator_goal:
        dimensions["business_context"] = 4
        score += dimensions["business_context"]
        strengths.append("business_context_declared")
    else:
        dimensions["business_context"] = 0
        gaps.append("missing_business_process_or_operator_goal")

    if manifest.maturity_level in {"L4", "L5"} and len(manifest_cases(manifest)) < 2:
        gaps.append("high_maturity_package_needs_multiple_cases")
    if (manifest.actual_maturity_level or manifest.maturity_level) in {"L0", "L1"} or manifest.evidence_kind in {"deterministic_synthetic", "domain_realistic_synthetic"}:
        gaps.append("synthetic_only_add_sanitized_local_trace_for_business_evidence")
    if benchmark.get("blockers"):
        gaps.append("benchmark_blockers_require_review")

    return min(score, 100), strengths, sorted(set(gaps), key=gaps.index), dimensions


def package_realism_report(package_dir: str | Path) -> dict[str, Any]:
    root = Path(package_dir)
    manifest = load_dataset_manifest(root)
    validation = validate_dataset_package(root)
    benchmark = benchmark_dataset_package(root)
    score, strengths, gaps, dimensions = _score_manifest(manifest, validation, benchmark)
    provenance = _load_provenance(root)
    cases = manifest_cases(manifest)
    evidence_level = EVIDENCE_KIND_LABELS.get(manifest.evidence_kind or "", MATURITY_EVIDENCE.get(manifest.maturity_level, "unknown"))
    synthetic = manifest.evidence_kind in {"deterministic_synthetic", "domain_realistic_synthetic"} or provenance.get("generated_by") == "host-screen-contracts"
    return {
        "schema_version": "1.0",
        "package_id": manifest.package_id,
        "transaction_id": manifest.transaction_id,
        "maturity_level": manifest.maturity_level,
        "actual_maturity_level": manifest.actual_maturity_level,
        "simulates_maturity_level": manifest.simulates_maturity_level,
        "evidence_kind": manifest.evidence_kind,
        "evidence_level": evidence_level,
        "synthetic": synthetic,
        "business_process": manifest.business_process,
        "operator_goal": manifest.operator_goal,
        "screen_family": manifest.screen_family,
        "data_origin": manifest.data_origin,
        "value_strategy": manifest.value_strategy,
        "known_limitations": manifest.known_limitations,
        "trace_count": len(cases),
        "case_ids": sorted(cases),
        "case_purposes": {case_id: case.purpose for case_id, case in sorted(cases.items())},
        "tags": sorted(manifest.tags),
        "business_impact_score": score,
        "score_dimensions": dimensions,
        "strengths": strengths,
        "gaps": gaps,
        "validation_ok": validation["ok"],
        "contract_ready_rate": benchmark["contract_ready_rate"],
        "review_required_count": benchmark["review_required_count"],
        "field_map_coverage": benchmark["field_map_coverage"],
        "warnings": validation["warnings"],
        "blockers": sorted(set(validation["blockers"] + benchmark["blockers"]), key=(validation["blockers"] + benchmark["blockers"]).index),
        "recommended_next_data": _recommended_next_data(manifest, gaps),
        "provenance": provenance,
    }


def _recommended_next_data(manifest: DatasetManifest, gaps: list[str]) -> list[str]:
    recommendations: list[str] = []
    if "synthetic_only_add_sanitized_local_trace_for_business_evidence" in gaps:
        recommendations.append("add_sanitized_local_trace_package_at_L2_or_higher")
    if "missing_negative_path" in gaps:
        recommendations.append("record_validation_error_or_not_found_case")
    if "missing_drift_or_change_signal" in gaps:
        recommendations.append("record_or_mutate_label_and_field_move_drift_case")
    if "field_map_coverage_below_80_percent" in gaps:
        recommendations.append("complete_field_map_for_request_and_response_fields")
    if manifest.maturity_level in {"L4", "L5"} and len(manifest_cases(manifest)) < 2:
        recommendations.append("add_multiple_cases_for_claimed_maturity_level")
    if not recommendations:
        recommendations.append("ready_for_human_contract_review")
    return recommendations


def corpus_realism_report(package_root: str | Path) -> dict[str, Any]:
    root = Path(package_root)
    packages = [package_realism_report(path) for path in sorted(root.glob("*/manifest.yml")) for path in [path.parent]]
    scores = [package["business_impact_score"] for package in packages]
    synthetic_count = sum(1 for package in packages if package["synthetic"])
    blocker_count = sum(1 for package in packages if package["blockers"])
    return {
        "schema_version": "1.0",
        "package_count": len(packages),
        "synthetic_package_count": synthetic_count,
        "blocker_package_count": blocker_count,
        "average_business_impact_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "portfolio": _portfolio_summary(packages),
        "packages": packages,
    }


def _portfolio_summary(packages: list[dict[str, Any]]) -> dict[str, Any]:
    def package_ids(predicate: Any) -> list[str]:
        return [package["package_id"] for package in packages if predicate(package)]

    contract_ready = package_ids(
        lambda package: not package["blockers"]
        and package["contract_ready_rate"] >= 0.5
        and package["business_impact_score"] >= 70
    )
    quick_wins = package_ids(
        lambda package: package["package_id"] in contract_ready
        and not {"subfile", "paging", "plain_text_only"}.intersection(package["tags"])
    )
    review_required = package_ids(
        lambda package: package["review_required_count"] > 0
        or bool(package["blockers"])
        or package["business_impact_score"] < 70
    )
    low_confidence = package_ids(
        lambda package: package["maturity_level"] == "L0"
        or package["business_impact_score"] < 40
        or "low_confidence" in package["tags"]
    )
    missing_field_map = package_ids(lambda package: package["field_map_coverage"] < 0.8)
    subfile_heavy = package_ids(lambda package: {"subfile", "paging"}.intersection(package["tags"]))
    privacy_review = package_ids(lambda package: {"sensitive", "hidden_field", "absent_hidden_field"}.intersection(package["tags"]))
    drift_prone = package_ids(lambda package: {"label_drift", "field_move_drift", "attribute_drift", "volatile_region"}.intersection(package["tags"]))
    navigation_setup = package_ids(lambda package: {"navigation", "menu"}.intersection(package["tags"]))
    boundary_locale = package_ids(lambda package: {"boundary_values", "locale_formats"}.intersection(package["tags"]))

    next_actions: list[str] = []
    if quick_wins:
        next_actions.append("review_quick_win_contracts_with_wrapper_team")
    if privacy_review:
        next_actions.append("sanitize_and_approve_privacy_review_before_sharing")
    if subfile_heavy:
        next_actions.append("schedule_human_review_for_subfile_selection_semantics")
    if missing_field_map:
        next_actions.append("complete_field_maps_before_treating_low_coverage_packages_as_api_candidates")
    if drift_prone:
        next_actions.append("use_drift_cases_to_define_wrapper_breakage_detection")
    if low_confidence:
        next_actions.append("replace_low_confidence_synthetic_cases_with_sanitized_local_traces")

    return {
        "contract_ready_candidates": contract_ready,
        "quick_win_candidates": quick_wins,
        "review_required_candidates": review_required,
        "low_confidence_candidates": low_confidence,
        "missing_field_map_candidates": missing_field_map,
        "subfile_heavy_candidates": subfile_heavy,
        "privacy_review_candidates": privacy_review,
        "drift_prone_candidates": drift_prone,
        "navigation_setup_candidates": navigation_setup,
        "boundary_locale_candidates": boundary_locale,
        "recommended_next_actions": next_actions or ["add_more_trace_packages"],
    }
