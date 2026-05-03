from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from stateful_storage_fit.engine import analyze_paths
from stateful_storage_fit.parse_extra import load_extra_evidence
from stateful_storage_fit.report import write_fit_result, write_mount_report
from stateful_storage_fit.validators import validate_decision, validate_input_realism
from stateful_storage_fit.workflow import bundle_paths, validate_bundle, validate_case


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _mount_report_columns(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        return next(reader)


def _resolve_case_path(case_path: Path, value: str | None, default: Path | None = None) -> Path | None:
    if not value:
        return default
    path = Path(value)
    return path if path.is_absolute() else (case_path.parent / path).resolve()


def audit_lab(lab_dir: Path, output_dir: Path) -> dict[str, Any]:
    default_profile = lab_dir / "storage-profile.yml"
    corpus_dir = lab_dir / "corpus"
    bundles_dir = lab_dir / "bundles"
    decisions_dir = output_dir / "decisions"
    mounts_dir = output_dir / "mount-reports"
    inputs_dir = output_dir / "input-realism"
    cases_dir = output_dir / "case-validations"
    decision_validations_dir = output_dir / "decision-validations"
    output_dir.mkdir(parents=True, exist_ok=True)

    status_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    capacity_counts: Counter[str] = Counter()
    latency_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    input_warnings: Counter[str] = Counter()
    case_issues: Counter[str] = Counter()
    decision_issues: Counter[str] = Counter()
    mount_column_sets: Counter[tuple[str, ...]] = Counter()
    rows: list[dict[str, Any]] = []

    for case_path in sorted(corpus_dir.glob("*.yml")):
        case = yaml.safe_load(case_path.read_text(encoding="utf-8")) or {}
        case_id = str(case.get("id") or case_path.stem)
        family = str((case.get("app_metadata") or {}).get("workload_family") or "unknown")
        bundle_value = (case.get("bundle") or {}).get("path")
        bundle_dir = _resolve_case_path(case_path, bundle_value, bundles_dir / case_id)
        if bundle_dir is None:
            continue
        profile = _resolve_case_path(case_path, case.get("storage_profile"), default_profile)
        policy_pack = _resolve_case_path(case_path, case.get("policy_pack"), None)
        path_purpose = bundle_dir / "path-purpose.yml"

        input_report = validate_input_realism(bundle_dir=bundle_dir, storage_profile=profile, path_purpose=path_purpose)
        _write_json(inputs_dir / f"{case_id}.json", input_report)
        for warning in input_report.get("warnings", []):
            input_warnings[warning] += 1

        paths = bundle_paths(bundle_dir)
        extra_evidence, extra_warnings = load_extra_evidence(
            findmnt_json=paths["findmnt_json"],
            lsblk_json=paths["lsblk_json"],
            blkid=paths["blkid"],
            pvs=paths["pvs"],
            vgs=paths["vgs"],
            lvs=paths["lvs"],
            inode_df=paths["inode_df"],
            du_summary=paths["du_summary"],
        )
        extra_evidence["bundle_validation"] = validate_bundle(bundle_dir)
        analysis = analyze_paths(
            df=paths["df"],
            mount=paths["mount"],
            fstab=paths["fstab"],
            iostat=paths["iostat"],
            ps=paths["ps"],
            storage_profile_path=profile,
            policy_pack_path=policy_pack,
            app_metadata=case.get("app_metadata") or {},
            extra_evidence=extra_evidence,
        )
        analysis.result.warnings.extend(warning for warning in extra_warnings if warning not in analysis.result.warnings)
        decision_path = decisions_dir / f"{case_id}.json"
        mount_report_path = mounts_dir / f"{case_id}.csv"
        write_fit_result(analysis.result, decision_path)
        write_mount_report(analysis.candidate_mounts, mount_report_path)

        decision_validation = validate_decision(decision_path)
        case_validation = validate_case(case_path)
        _write_json(decision_validations_dir / f"{case_id}.json", decision_validation)
        _write_json(cases_dir / f"{case_id}.json", case_validation)

        for issue in decision_validation.get("issues", []):
            decision_issues[issue] += 1
        for issue in case_validation.get("issues", []):
            case_issues[issue] += 1

        result = analysis.result
        status_counts[result.fit_status] += 1
        confidence_counts[result.confidence] += 1
        capacity_counts[result.capacity_risk] += 1
        latency_counts[result.latency_risk] += 1
        family_counts[family] += 1
        for code in result.reason_codes:
            reason_counts[code] += 1
        for warning in result.warnings:
            warning_counts[warning] += 1
        for blocker in result.blockers:
            blocker_counts[blocker] += 1
        mount_column_sets[tuple(_mount_report_columns(mount_report_path))] += 1
        rows.append(
            {
                "case_id": case_id,
                "family": family,
                "fit_status": result.fit_status,
                "recommended_storage_class": result.recommended_storage_class,
                "capacity_risk": result.capacity_risk,
                "latency_risk": result.latency_risk,
                "confidence": result.confidence,
                "reason_codes": result.reason_codes,
                "warnings": result.warnings,
                "blockers": result.blockers,
                "input_valid": input_report.get("valid"),
                "input_warnings": input_report.get("warnings", []),
                "bundle_quality": (input_report.get("bundle_validation") or {}).get("overall_bundle_quality_score"),
                "path_purpose_quality": input_report.get("path_purpose_quality_score"),
                "decision_valid": decision_validation.get("valid"),
                "case_valid": case_validation.get("valid"),
                "trusted_label": case_validation.get("trusted_label"),
                "calibration_ready": case_validation.get("calibration_ready"),
            }
        )

    summary = {
        "schema_version": "1.0",
        "lab_dir": str(lab_dir),
        "case_count": len(rows),
        "family_counts": dict(sorted(family_counts.items())),
        "fit_status_counts": dict(sorted(status_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "capacity_risk_counts": dict(sorted(capacity_counts.items())),
        "latency_risk_counts": dict(sorted(latency_counts.items())),
        "reason_code_counts": dict(sorted(reason_counts.items())),
        "warning_counts": dict(sorted(warning_counts.items())),
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "input_warning_counts": dict(sorted(input_warnings.items())),
        "decision_issue_counts": dict(sorted(decision_issues.items())),
        "case_issue_counts": dict(sorted(case_issues.items())),
        "all_inputs_valid": all(row["input_valid"] for row in rows),
        "all_decisions_valid": all(row["decision_valid"] for row in rows),
        "all_cases_valid": all(row["case_valid"] for row in rows),
        "trusted_label_count": sum(1 for row in rows if row["trusted_label"]),
        "calibration_ready_count": sum(1 for row in rows if row["calibration_ready"]),
        "min_bundle_quality": min(row["bundle_quality"] for row in rows),
        "min_path_purpose_quality": min(row["path_purpose_quality"] for row in rows),
        "mount_report_column_sets": [
            {"columns": list(columns), "count": count}
            for columns, count in sorted(mount_column_sets.items(), key=lambda item: item[0])
        ],
        "rows": rows,
    }
    _write_json(output_dir / "lab-audit-summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lab-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_lab(args.lab_dir, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
