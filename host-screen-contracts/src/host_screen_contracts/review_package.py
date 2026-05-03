from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from .benchmark import benchmark_dataset_package
from .bundle_score import score_bundle_inputs
from .dataset_model import load_dataset_manifest, manifest_cases
from .dataset_validate import validate_dataset_package
from .executive_summary import render_executive_summary
from .field_map import load_field_map
from .openapi_validate import validate_openapi_file
from .package_extract import extract_dataset_package
from .parse_trace import load_trace
from .privacy_report import generate_privacy_report
from .readiness import assess_review_readiness
from .realism_report import package_realism_report
from .report import write_json, write_text


def _highest_severity(values: list[str | None]) -> str | None:
    for severity in ("HIGH", "MEDIUM", "LOW"):
        if severity in values:
            return severity
    return None


def _aggregate_privacy(package_dir: Path, output_dir: Path) -> dict[str, Any]:
    manifest = load_dataset_manifest(package_dir)
    cases = manifest_cases(manifest)
    field_map = load_field_map(package_dir / manifest.field_map) if manifest.field_map else None
    privacy_dir = output_dir / "privacy"
    privacy_dir.mkdir(parents=True, exist_ok=True)
    reports: list[dict[str, Any]] = []
    report_paths: dict[str, str] = {}
    for case_id, case in cases.items():
        case_field_map = field_map.for_case(case_id) if field_map else None
        report = generate_privacy_report(load_trace(package_dir / case.trace), case_field_map)
        report_path = privacy_dir / f"{case_id}.privacy.json"
        write_json(report_path, report)
        report_paths[case_id] = str(report_path)
        reports.append(report)

    aggregate = {
        "schema_version": "1.0",
        "case_count": len(reports),
        "unredacted_sensitive_value_count": sum(report["unredacted_sensitive_value_count"] for report in reports),
        "confirmed_sensitive_unredacted_count": sum(report.get("confirmed_sensitive_unredacted_count", 0) for report in reports),
        "potential_identifier_pattern_count": sum(report.get("potential_identifier_pattern_count", 0) for report in reports),
        "hidden_field_unredacted_count": sum(report.get("hidden_field_unredacted_count", 0) for report in reports),
        "highest_unredacted_severity": _highest_severity([report.get("highest_unredacted_severity") for report in reports]),
        "case_reports": report_paths,
    }
    write_json(output_dir / "privacy_report.json", aggregate)
    return aggregate


def _write_bundle(output_dir: Path, extraction: dict[str, Any], readiness_path: Path, summary_path: Path, privacy_path: Path) -> dict[str, Any]:
    bundle_path = output_dir / "review_package.zip"
    replay_case_path: Path | None = None
    canonical_case_ids = extraction.get("canonical_case_ids") or []
    if canonical_case_ids:
        candidate = output_dir / "cases" / f"{canonical_case_ids[0]}.case.yml"
        if candidate.exists():
            replay_case_path = candidate
    files = {
        "contract.yml": Path(extraction["canonical_contract"]) if extraction.get("canonical_contract") else None,
        "openapi.yml": Path(extraction["api_candidate"]) if extraction.get("api_candidate") else None,
        "replay_case.yml": replay_case_path,
        "replay_test.py": Path(extraction["combined_replay_test"]) if extraction.get("combined_replay_test") else None,
        "summary.json": readiness_path,
        "privacy_report.json": privacy_path,
    }
    supporting_files = {
        "executive_summary.md": summary_path,
        "drift_evidence.yml": Path(extraction["drift_evidence"]) if extraction.get("drift_evidence") else None,
        "flow_graph.yml": Path(extraction["flow_graph"]) if extraction.get("flow_graph") else None,
        "openapi_validation.json": output_dir / "openapi_validation.json",
    }
    completeness = score_bundle_inputs(files)
    manifest = {
        "schema_version": "1.0",
        "generated_by": "host-screen-contracts",
        "bundle_kind": "review_package",
        "files": sorted(name for name, path in files.items() if path is not None),
        "additional_files": sorted(name for name, path in supporting_files.items() if path is not None and path.exists()),
        "completeness": completeness,
    }
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for archive_name, path in files.items():
            if path is not None:
                bundle.write(path, archive_name)
        for archive_name, path in supporting_files.items():
            if path is not None and path.exists():
                bundle.write(path, archive_name)
        bundle.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
    return {"path": str(bundle_path), "completeness": completeness}


def build_review_package(
    package_dir: str | Path,
    *,
    output_dir: str | Path,
    strict: bool = False,
) -> dict[str, Any]:
    package = Path(package_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest = load_dataset_manifest(package)

    validation = validate_dataset_package(package, strict=strict)
    benchmark = benchmark_dataset_package(package)
    extraction = extract_dataset_package(
        package,
        output_dir=output,
        output_summary=output / "extraction_summary.json",
        strict=strict,
    )
    openapi_errors = validate_openapi_file(extraction["api_candidate"])
    openapi_validation = {
        "schema_version": "1.0",
        "ok": not openapi_errors,
        "local_errors": openapi_errors,
    }
    write_json(output / "openapi_validation.json", openapi_validation)
    realism = package_realism_report(package)
    privacy = _aggregate_privacy(package, output)
    readiness = assess_review_readiness(
        validation=validation,
        benchmark=benchmark,
        extraction=extraction,
        realism=realism,
        privacy=privacy,
        openapi_validation=openapi_validation,
    )
    readiness_path = output / "readiness.json"
    write_json(readiness_path, readiness)
    executive = render_executive_summary(
        package_id=manifest.package_id,
        transaction_id=manifest.transaction_id,
        readiness=readiness,
        realism=realism,
        extraction=extraction,
        privacy=privacy,
        validation=validation,
        benchmark=benchmark,
    )
    executive_path = output / "executive_summary.md"
    write_text(executive_path, executive)
    bundle = _write_bundle(output, extraction, readiness_path, executive_path, output / "privacy_report.json")
    result = {
        "schema_version": "1.0",
        "package_id": manifest.package_id,
        "transaction_id": manifest.transaction_id,
        "review_package_status": readiness["review_package_status"],
        "output_dir": str(output),
        "readiness": str(readiness_path),
        "executive_summary": str(executive_path),
        "bundle": bundle,
        "canonical_contract": extraction.get("canonical_contract"),
        "api_candidate": extraction.get("api_candidate"),
        "drift_evidence": extraction.get("drift_evidence"),
        "flow_graph": extraction.get("flow_graph"),
        "blockers": readiness["blockers"],
        "review_items": readiness["review_items"],
    }
    write_json(output / "review_package.json", result)
    if strict and result["blockers"]:
        result["ok"] = False
    else:
        result["ok"] = not result["blockers"]
    return result
