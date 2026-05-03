from __future__ import annotations

from typing import Any


def assess_review_readiness(
    *,
    validation: dict[str, Any],
    benchmark: dict[str, Any],
    extraction: dict[str, Any],
    realism: dict[str, Any],
    privacy: dict[str, Any],
    openapi_validation: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    review_items: list[str] = []

    blockers.extend(validation.get("blockers", []))
    blockers.extend(extraction.get("blockers", []))
    if not openapi_validation.get("ok", False):
        blockers.append("OPENAPI_VALIDATION_FAILED")

    if validation.get("warnings"):
        review_items.append("validation_warnings_present")
    if extraction.get("warnings"):
        review_items.append("extraction_warnings_present")
    if benchmark.get("review_required_count", 0):
        review_items.append("case_review_required")
    if benchmark.get("field_map_coverage", 0) < 1:
        review_items.append("field_map_not_complete")
    if privacy.get("unredacted_sensitive_value_count", 0):
        review_items.append("privacy_review_required")
    if realism.get("synthetic"):
        review_items.append("synthetic_evidence_requires_local_trace_validation")
    if extraction.get("drift_case_count", 0):
        review_items.append("drift_evidence_present")
    if extraction.get("non_contract_case_count", 0):
        review_items.append("non_contract_cases_present")

    if blockers:
        status = "blocked"
    elif review_items:
        status = "review_required"
    else:
        status = "ready_for_review"

    dimensions = {
        "package_valid": bool(validation.get("ok")),
        "openapi_valid": bool(openapi_validation.get("ok")),
        "contract_ready_rate": benchmark.get("contract_ready_rate", 0),
        "field_map_coverage": benchmark.get("field_map_coverage", 0),
        "privacy_unredacted_count": privacy.get("unredacted_sensitive_value_count", 0),
        "business_impact_score": realism.get("business_impact_score", 0),
        "canonical_case_count": extraction.get("canonical_case_count", 0),
        "drift_case_count": extraction.get("drift_case_count", 0),
        "non_contract_case_count": extraction.get("non_contract_case_count", 0),
    }

    next_actions = list(realism.get("recommended_next_data", []))
    if privacy.get("unredacted_sensitive_value_count", 0):
        next_actions.insert(0, "sanitize_or_tokenize_trace_values_before_sharing")
    if extraction.get("drift_case_count", 0):
        next_actions.append("review_drift_evidence_before_using_contract_as_baseline")
    if extraction.get("non_contract_case_count", 0):
        next_actions.append("keep_navigation_cancel_paths_out_of_api_contract_shape")

    return {
        "schema_version": "1.0",
        "review_package_status": status,
        "blockers": sorted(set(blockers), key=blockers.index),
        "review_items": sorted(set(review_items), key=review_items.index),
        "dimensions": dimensions,
        "recommended_next_actions": sorted(set(next_actions), key=next_actions.index),
    }
