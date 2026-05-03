from __future__ import annotations

from pathlib import Path
from typing import Any

from .contract_model import ReplayCaseSummary, ScreenFieldContract, TransactionContract, contract_to_dict
from .dataset_model import DatasetCase, infer_case_kind, load_dataset_manifest, manifest_cases
from .drift_compare import compare_contract_to_trace
from .drift_baseline import generate_drift_baseline
from .field_map import load_field_map
from .flow_graph import build_flow_graph
from .flow_extract import ExtractionResult, extract_transaction
from .models import BlockerCode
from .openapi_gen import generate_openapi
from .parse_trace import load_trace
from .replay_gen import generate_package_pytest
from .replay_model import replay_case_to_dict
from .report import write_json, write_text, write_yaml


def _field_key(field: ScreenFieldContract) -> tuple[str, str | None, int, int, str]:
    return (field.screen_ref, field.field_id, field.row, field.col, field.name)


def _merge_fields(base: list[ScreenFieldContract], extra: list[ScreenFieldContract]) -> list[ScreenFieldContract]:
    merged = list(base)
    seen = {_field_key(field) for field in merged}
    for field in extra:
        key = _field_key(field)
        if key not in seen:
            seen.add(key)
            merged.append(field)
    return merged


def _merge_screens(base: list, extra: list) -> list:
    merged = list(base)
    seen = {(screen.screen_ref, screen.screen_hash) for screen in merged}
    for screen in extra:
        key = (screen.screen_ref, screen.screen_hash)
        if key not in seen:
            seen.add(key)
            merged.append(screen)
    return merged


def _merge_transitions(base: list, extra: list) -> list:
    merged = list(base)
    seen = {
        (
            transition.from_screen_ref,
            transition.aid,
            transition.to_screen_ref,
            transition.expected_to_screen_hash,
            tuple(sorted(transition.input_values.items())),
        )
        for transition in merged
    }
    for transition in extra:
        key = (
            transition.from_screen_ref,
            transition.aid,
            transition.to_screen_ref,
            transition.expected_to_screen_hash,
            tuple(sorted(transition.input_values.items())),
        )
        if key not in seen:
            seen.add(key)
            merged.append(transition)
    return merged


def _case_kind(case_id: str, case: DatasetCase) -> str:
    return case.case_kind or infer_case_kind(case_id)


def _canonical_case(case: DatasetCase) -> bool:
    return case.purpose in {"canonical_success", "canonical_error", "recorded_path", "navigation", "guardrail"}


def _merge_contracts(
    results: list[tuple[str, DatasetCase, ExtractionResult]],
    *,
    include_non_contract_warnings: bool = True,
) -> TransactionContract:
    combined = results[0][2].contract.model_copy(deep=True)
    combined.replay_cases = []
    all_warnings: list[str] = []
    all_blockers: list[str] = []
    for case_id, case, result in results:
        combined.screens = _merge_screens(combined.screens, result.contract.screens)
        combined.transitions = _merge_transitions(combined.transitions, result.contract.transitions)
        combined.request_fields = _merge_fields(combined.request_fields, result.contract.request_fields)
        combined.response_fields = _merge_fields(combined.response_fields, result.contract.response_fields)
        combined.replay_cases.append(
            ReplayCaseSummary(
                case_id=result.replay_case.case_id,
                case_kind=result.replay_case.case_kind,
                start_screen_hash=result.replay_case.start_screen_hash,
            )
        )
        all_warnings.extend(f"{case_id}:{warning}" for warning in result.contract.warnings)
        for blocker in result.contract.blockers:
            if include_non_contract_warnings and case.purpose == "non_contract" and blocker in {
                BlockerCode.NO_INPUT_FIELDS.value,
                BlockerCode.NO_FINAL_OUTPUT_FIELDS.value,
            }:
                all_warnings.append(f"{case_id}:NON_CONTRACT_CASE:{blocker}")
            else:
                all_blockers.append(f"{case_id}:{blocker}")
    combined.warnings = sorted(set(all_warnings), key=all_warnings.index)
    combined.blockers = sorted(set(all_blockers), key=all_blockers.index)
    combined.flow_graph = build_flow_graph(
        [(case_id, result.replay_case.case_kind, result.contract) for case_id, _case, result in results]
    )
    return combined


def _drift_evidence(
    root: Path,
    canonical_baseline: TransactionContract | None,
    cases: list[tuple[str, DatasetCase, ExtractionResult]],
    field_map: Any,
) -> dict[str, Any]:
    drift_cases = [(case_id, case, result) for case_id, case, result in cases if case.purpose == "drift_evidence"]
    evidence: list[dict[str, Any]] = []
    for case_id, case, result in drift_cases:
        item: dict[str, Any] = {
            "case_id": case_id,
            "case_kind": result.replay_case.case_kind,
            "trace": case.trace,
            "purpose": case.purpose,
            "warnings": result.contract.warnings,
            "blockers": result.contract.blockers,
        }
        if canonical_baseline is not None:
            try:
                item["comparison_to_canonical"] = compare_contract_to_trace(
                    canonical_baseline,
                    load_trace(root / case.trace),
                    field_map=field_map,
                )
            except Exception as exc:  # noqa: BLE001 - evidence should remain reportable
                item["comparison_to_canonical"] = {
                    "status": "comparison_failed",
                    "error": str(exc),
                }
        evidence.append(item)
    return {
        "schema_version": "1.0",
        "drift_case_count": len(evidence),
        "drift_cases": evidence,
    }


def extract_dataset_package(
    package_dir: str | Path,
    *,
    output_dir: str | Path,
    output_contract: str | Path | None = None,
    output_openapi: str | Path | None = None,
    output_replay_test: str | Path | None = None,
    output_drift_baseline: str | Path | None = None,
    output_summary: str | Path | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    root = Path(package_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest = load_dataset_manifest(root)
    field_map = load_field_map(root / manifest.field_map) if manifest.field_map else None
    case_defs = manifest_cases(manifest)
    results: list[tuple[str, DatasetCase, ExtractionResult]] = []
    replay_test_cases: list[tuple[str, Path, Path]] = []
    case_contract_dir = output / "case_contracts"
    case_dir = output / "cases"
    case_contract_dir.mkdir(parents=True, exist_ok=True)
    case_dir.mkdir(parents=True, exist_ok=True)
    for case_id, case in case_defs.items():
        case_kind = _case_kind(case_id, case)
        case_field_map = field_map.for_case(case_id) if field_map else None
        result = extract_transaction(
            load_trace(root / case.trace),
            transaction_id=manifest.transaction_id,
            case_id=case_id,
            case_kind=case_kind,
            field_map=case_field_map,
            strict=strict,
            output_paths={},
        )
        results.append((case_id, case, result))
        case_path = output / f"{case_id}.case.yml"
        structured_case_path = case_dir / f"{case_id}.case.yml"
        write_yaml(case_path, replay_case_to_dict(result.replay_case))
        write_yaml(structured_case_path, replay_case_to_dict(result.replay_case))
        write_yaml(output / f"{case_id}.contract.yml", contract_to_dict(result.contract))
        write_yaml(case_contract_dir / f"{case_id}.contract.yml", contract_to_dict(result.contract))
        if _canonical_case(case):
            replay_test_cases.append((case_id, root / case.trace, case_path))

    if not results:
        summary = {
            "schema_version": "1.0",
            "package_id": manifest.package_id,
            "transaction_id": manifest.transaction_id,
            "case_count": 0,
            "blockers": ["NO_TRACE_CASES"],
        }
        if output_summary:
            write_json(output_summary, summary)
        return summary

    canonical_results = [(case_id, case, result) for case_id, case, result in results if _canonical_case(case)]
    if not canonical_results:
        canonical_results = results
        replay_test_cases = [
            (case_id, root / case.trace, output / f"{case_id}.case.yml")
            for case_id, case, _result in results
        ]
    combined = _merge_contracts(canonical_results)
    canonical_success_baseline = next(
        (
            result.contract
            for _case_id, case, result in canonical_results
            if case.purpose == "canonical_success"
        ),
        canonical_results[0][2].contract if canonical_results else None,
    )
    all_case_graph = build_flow_graph(
        [(case_id, result.replay_case.case_kind, result.contract) for case_id, _case, result in results]
    )

    contract_path = Path(output_contract) if output_contract else output / "transaction.contract.yml"
    openapi_path = Path(output_openapi) if output_openapi else output / "transaction.openapi.yml"
    replay_test_path = Path(output_replay_test) if output_replay_test else output / "test_transaction_replay.py"
    drift_baseline_path = Path(output_drift_baseline) if output_drift_baseline else output / "transaction.drift-baseline.json"
    canonical_contract_path = output / "canonical_contract.yml"
    api_candidate_path = output / "api_candidate.openapi.yml"
    flow_graph_path = output / "flow_graph.yml"
    drift_evidence_path = output / "drift_evidence.yml"
    write_yaml(contract_path, contract_to_dict(combined))
    write_yaml(canonical_contract_path, contract_to_dict(combined))
    write_yaml(openapi_path, generate_openapi(combined))
    write_yaml(api_candidate_path, generate_openapi(combined))
    write_text(replay_test_path, generate_package_pytest(contract_path, replay_test_cases))
    write_json(drift_baseline_path, generate_drift_baseline(combined))
    write_yaml(flow_graph_path, all_case_graph)
    write_yaml(drift_evidence_path, _drift_evidence(root, canonical_success_baseline, results, field_map))
    purpose_counts: dict[str, int] = {}
    for _case_id, case, _result in results:
        purpose_counts[case.purpose] = purpose_counts.get(case.purpose, 0) + 1
    summary = {
        "schema_version": "1.0",
        "package_id": manifest.package_id,
        "transaction_id": manifest.transaction_id,
        "case_count": len(results),
        "canonical_case_count": len(canonical_results),
        "drift_case_count": purpose_counts.get("drift_evidence", 0),
        "non_contract_case_count": purpose_counts.get("non_contract", 0),
        "case_purpose_counts": purpose_counts,
        "case_ids": [case_id for case_id, _case, _result in results],
        "canonical_case_ids": [case_id for case_id, _case, _result in canonical_results],
        "combined_contract": str(contract_path),
        "canonical_contract": str(canonical_contract_path),
        "combined_openapi": str(openapi_path),
        "api_candidate": str(api_candidate_path),
        "combined_replay_test": str(replay_test_path),
        "drift_baseline": str(drift_baseline_path),
        "drift_evidence": str(drift_evidence_path),
        "flow_graph": str(flow_graph_path),
        "request_field_count": len(combined.request_fields),
        "response_field_count": len(combined.response_fields),
        "replay_case_count": len(combined.replay_cases),
        "warnings": combined.warnings,
        "blockers": combined.blockers,
        "fit_for_review": not combined.blockers,
    }
    if output_summary:
        write_json(output_summary, summary)
    return summary
