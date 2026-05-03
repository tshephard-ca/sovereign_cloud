from __future__ import annotations

from pathlib import Path
from statistics import median
from typing import Any

from .dataset_model import manifest_cases, load_dataset_manifest
from .dataset_validate import validate_dataset_package
from .field_map import load_field_map
from .flow_extract import extract_transaction
from .models import BlockerCode, WarningCode
from .parse_trace import load_trace


HIGH_RISK_WARNINGS = {
    WarningCode.SUBFILE_LIKE_REGION_DETECTED.value,
    WarningCode.PLAIN_TEXT_ONLY_TRACE.value,
    WarningCode.GENERATED_COORDINATE_NAMES.value,
    "FIELD_MAP_INVALID",
}


def benchmark_dataset_package(package_dir: str | Path) -> dict[str, Any]:
    root = Path(package_dir)
    validation = validate_dataset_package(root)
    try:
        manifest = load_dataset_manifest(root)
    except Exception as exc:  # noqa: BLE001 - benchmark should not crash on adversarial packages
        return {
            "schema_version": "1.0",
            "package_id": root.name,
            "transaction_id": "",
            "maturity_level": "",
            "validation_ok": False,
            "trace_count": 0,
            "contract_ready_count": 0,
            "contract_ready_rate": 0,
            "review_required_count": 0,
            "median_request_fields": 0,
            "median_response_fields": 0,
            "field_map_coverage": 0,
            "generated_coordinate_names": 0,
            "inferred_label_names": 0,
            "warnings": validation.get("warnings", []),
            "blockers": validation.get("blockers", []) + [f"MANIFEST_INVALID:{str(exc).splitlines()[0]}"],
            "case_summaries": [],
        }
    try:
        field_map = load_field_map(root / manifest.field_map) if manifest.field_map and (root / manifest.field_map).exists() else None
    except Exception as exc:  # noqa: BLE001 - keep benchmark reporting usable
        field_map = None
        validation["blockers"].append(f"FIELD_MAP_INVALID:{str(exc).splitlines()[0]}")
    summaries: list[dict[str, Any]] = []
    extraction_warnings: list[str] = []
    extraction_blockers: list[str] = []
    cases = manifest_cases(manifest)
    for case_id, case in cases.items():
        trace_path = root / case.trace
        if not trace_path.exists():
            continue
        try:
            events = load_trace(trace_path)
        except Exception as exc:  # noqa: BLE001 - benchmark should report invalid cases
            extraction_blockers.append(f"{case_id}:TRACE_PARSE_FAILED:{exc}")
            continue
        result = extract_transaction(
            events,
            transaction_id=manifest.transaction_id,
            case_id=case_id,
            case_kind=case_id,
            field_map=field_map.for_case(case_id) if field_map else None,
            output_paths={},
        )
        extraction_warnings.extend(f"{case_id}:extract:{warning}" for warning in result.contract.warnings)
        for blocker in result.contract.blockers:
            if "cancel" in case_id.lower() and blocker in {
                BlockerCode.NO_INPUT_FIELDS.value,
                BlockerCode.NO_FINAL_OUTPUT_FIELDS.value,
            }:
                extraction_warnings.append(f"{case_id}:NON_CONTRACT_CANCEL_CASE:{blocker}")
            else:
                extraction_blockers.append(f"{case_id}:extract:{blocker}")
        summary = result.summary.copy()
        summary["case_id"] = case_id
        summaries.append(summary)

    request_counts = [summary["request_field_count"] for summary in summaries]
    response_counts = [summary["response_field_count"] for summary in summaries]
    strict_ready = [
        summary
        for summary in summaries
        if summary["fit_for_review"]
        and summary["confidence"] == "HIGH"
        and not set(summary["warnings"]).intersection(HIGH_RISK_WARNINGS)
        and not summary["blockers"]
    ]
    field_map_names = sum(summary["field_map_names"] for summary in summaries)
    total_fields = sum(summary["request_field_count"] + summary["response_field_count"] for summary in summaries)
    all_warnings = validation["warnings"] + extraction_warnings
    all_blockers = validation["blockers"] + extraction_blockers
    warnings = sorted(set(all_warnings), key=all_warnings.index)
    blockers = sorted(set(all_blockers), key=all_blockers.index)
    return {
        "schema_version": "1.0",
        "package_id": manifest.package_id,
        "transaction_id": manifest.transaction_id,
        "maturity_level": manifest.maturity_level,
        "evidence_kind": manifest.evidence_kind,
        "actual_maturity_level": manifest.actual_maturity_level,
        "simulates_maturity_level": manifest.simulates_maturity_level,
        "validation_ok": validation["ok"],
        "trace_count": len(summaries),
        "contract_ready_count": len(strict_ready),
        "contract_ready_rate": (len(strict_ready) / len(summaries)) if summaries else 0,
        "review_required_count": max(len(summaries) - len(strict_ready), 0),
        "median_request_fields": median(request_counts) if request_counts else 0,
        "median_response_fields": median(response_counts) if response_counts else 0,
        "field_map_coverage": (field_map_names / total_fields) if total_fields else 0,
        "generated_coordinate_names": sum(summary["generated_coordinate_names"] for summary in summaries),
        "inferred_label_names": sum(summary["inferred_label_names"] for summary in summaries),
        "warnings": warnings,
        "blockers": blockers,
        "case_summaries": summaries,
    }
