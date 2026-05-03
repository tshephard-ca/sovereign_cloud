"""Estate Evidence Bundle workflow."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from estate_triage.adapters import (
    AdapterResult,
    merge_evidence_sets,
    read_backup_evidence_csv,
    read_inventory_evidence_csv,
    read_utilization_evidence_csv,
)
from estate_triage.api import analyze_estate
from estate_triage.assessment import AssessmentResult, RankingMode, rank_assessments
from estate_triage.config import load_thresholds
from estate_triage.evidence import DataQualityFinding, SourceRef
from estate_triage.fingerprint import InputFingerprint, fingerprint_csv, write_fingerprints
from estate_triage.identity import load_identity_overrides
from estate_triage.mapping import ColumnMapping, MappingKind, headers_for, load_column_mapping
from estate_triage.models import TriageError
from estate_triage.normalize import parse_datetime
from estate_triage.policy import load_policy_pack
from estate_triage.privacy import PrivacyMode
from estate_triage.report import write_assessment_json, write_results_csv, write_summary_json
from estate_triage.validation import (
    MappingApproval,
    ReadinessAction,
    ValidationReport,
    validation_report,
    write_validation_report,
)
from estate_triage.workflow import workflow_summary


BUNDLE_SCHEMA_VERSION = "1.0.0"


class BundleInput(BaseModel):
    path: str
    kind: MappingKind
    mapping: str | None = None


class BundlePolicy(BaseModel):
    thresholds: str | None = None
    policy_pack: str | None = None


class BundlePrivacy(BaseModel):
    redaction_mode: PrivacyMode = "standard"
    hash_salt_file: str | None = None


class BundleOutputs(BaseModel):
    directory: str = "outputs"
    top_csv: str = "top.csv"
    summary_json: str = "summary.json"
    assessment_json: str = "assessment.json"
    validation_json: str = "validation.json"
    fingerprints_json: str = "input-fingerprints.json"


class FeedbackItem(BaseModel):
    workload_key: str
    finding: str
    outcome: Literal[
        "accepted",
        "rejected",
        "needs_more_data",
        "duplicate",
        "wrong_motion",
        "missed_opportunity",
        "useful",
        "not_useful",
        "false_positive",
        "wrong_match",
        "already_known",
    ]
    converted: bool = False
    next_step: Literal[
        "none",
        "discovery_call",
        "deeper_assessment",
        "technical_workshop",
        "work_item",
        "other",
    ] = "none"
    reason: str | None = None
    notes: str | None = None


class FeedbackFile(BaseModel):
    assessment_id: str
    manual_triage_minutes: float | None = None
    tool_triage_minutes: float | None = None
    feedback: list[FeedbackItem] = Field(default_factory=list)


class EstateBundleManifest(BaseModel):
    bundle_version: str = BUNDLE_SCHEMA_VERSION
    assessment_id: str
    inputs: list[BundleInput]
    policy: BundlePolicy = Field(default_factory=BundlePolicy)
    privacy: BundlePrivacy = Field(default_factory=BundlePrivacy)
    outputs: BundleOutputs = Field(default_factory=BundleOutputs)
    feedback: str | None = None
    identity_overrides: str | None = None


class BundleRunResult(BaseModel):
    assessment: AssessmentResult
    summary: dict
    validation_reports: list[ValidationReport]
    fingerprints: list[InputFingerprint]
    feedback_summary: dict


def load_manifest(bundle_dir: Path) -> EstateBundleManifest:
    manifest_path = bundle_dir / "manifest.yml"
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise TriageError(f"Could not read bundle manifest {manifest_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise TriageError(f"Could not parse bundle manifest {manifest_path}: {exc}") from exc
    try:
        return EstateBundleManifest(**raw)
    except Exception as exc:
        raise TriageError(f"Invalid bundle manifest {manifest_path}: {exc}") from exc


def _salt(bundle_dir: Path, privacy: BundlePrivacy) -> str:
    if privacy.hash_salt_file is None:
        return ""
    path = bundle_dir / privacy.hash_salt_file
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("estate-triage-local-salt\n", encoding="utf-8")
    return path.read_text(encoding="utf-8")


def _read_feedback(bundle_dir: Path, manifest: EstateBundleManifest) -> FeedbackFile | None:
    if manifest.feedback is None:
        return None
    path = bundle_dir / manifest.feedback
    if not path.exists():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return FeedbackFile(**raw)
    except Exception as exc:
        raise TriageError(f"Invalid feedback file {path}: {exc}") from exc


def summarize_feedback(feedback: FeedbackFile | None) -> dict:
    outcomes = {
        "accepted": 0,
        "rejected": 0,
        "needs_more_data": 0,
        "duplicate": 0,
        "wrong_motion": 0,
        "missed_opportunity": 0,
        "useful": 0,
        "not_useful": 0,
        "false_positive": 0,
        "wrong_match": 0,
        "already_known": 0,
    }
    next_steps = {
        "none": 0,
        "discovery_call": 0,
        "deeper_assessment": 0,
        "technical_workshop": 0,
        "work_item": 0,
        "other": 0,
    }
    converted = 0
    if feedback is not None:
        for item in feedback.feedback:
            outcomes[item.outcome] += 1
            next_steps[item.next_step] += 1
            if item.converted:
                converted += 1
    item_count = 0 if feedback is None else len(feedback.feedback)
    reviewed_count = item_count - outcomes["missed_opportunity"]
    false_positive_count = outcomes["false_positive"] + outcomes["wrong_match"]
    rejected_count = outcomes["rejected"] + outcomes["not_useful"] + false_positive_count
    accepted_count = outcomes["accepted"] + outcomes["useful"]
    manual_minutes = None if feedback is None else feedback.manual_triage_minutes
    tool_minutes = None if feedback is None else feedback.tool_triage_minutes
    time_saved = None
    time_saved_pct = None
    if manual_minutes is not None and tool_minutes is not None:
        time_saved = manual_minutes - tool_minutes
        if manual_minutes > 0:
            time_saved_pct = round((time_saved / manual_minutes) * 100, 2)
    return {
        "assessment_id": None if feedback is None else feedback.assessment_id,
        "items": item_count,
        "reviewed_items": reviewed_count,
        "outcomes": outcomes,
        "rates": {
            "accepted_rate": round(accepted_count / reviewed_count, 4) if reviewed_count else None,
            "rejected_rate": round(rejected_count / reviewed_count, 4) if reviewed_count else None,
            "false_positive_rate": round(false_positive_count / reviewed_count, 4) if reviewed_count else None,
            "false_negative_count": outcomes["missed_opportunity"],
            "conversion_rate": round(converted / reviewed_count, 4) if reviewed_count else None,
        },
        "conversion": {
            "converted": converted,
            "next_steps": next_steps,
        },
        "time_benchmark": {
            "manual_triage_minutes": manual_minutes,
            "tool_triage_minutes": tool_minutes,
            "time_saved_minutes": time_saved,
            "time_saved_pct": time_saved_pct,
        },
    }


def summarize_feedback_ledger(feedback_files: list[FeedbackFile]) -> dict:
    summaries = [summarize_feedback(feedback) for feedback in feedback_files]
    aggregate_outcomes: dict[str, int] = {}
    aggregate_next_steps: dict[str, int] = {}
    total_items = 0
    total_reviewed = 0
    total_converted = 0
    total_manual = 0.0
    total_tool = 0.0
    has_time = False
    for summary in summaries:
        total_items += summary["items"]
        total_reviewed += summary["reviewed_items"]
        total_converted += summary["conversion"]["converted"]
        for key, value in summary["outcomes"].items():
            aggregate_outcomes[key] = aggregate_outcomes.get(key, 0) + value
        for key, value in summary["conversion"]["next_steps"].items():
            aggregate_next_steps[key] = aggregate_next_steps.get(key, 0) + value
        benchmark = summary["time_benchmark"]
        if benchmark["manual_triage_minutes"] is not None and benchmark["tool_triage_minutes"] is not None:
            has_time = True
            total_manual += benchmark["manual_triage_minutes"]
            total_tool += benchmark["tool_triage_minutes"]
    false_positive_count = aggregate_outcomes.get("false_positive", 0) + aggregate_outcomes.get("wrong_match", 0)
    accepted_count = aggregate_outcomes.get("accepted", 0) + aggregate_outcomes.get("useful", 0)
    rejected_count = (
        aggregate_outcomes.get("rejected", 0)
        + aggregate_outcomes.get("not_useful", 0)
        + false_positive_count
    )
    time_saved = total_manual - total_tool if has_time else None
    return {
        "assessments": len(summaries),
        "items": total_items,
        "reviewed_items": total_reviewed,
        "outcomes": dict(sorted(aggregate_outcomes.items())),
        "rates": {
            "accepted_rate": round(accepted_count / total_reviewed, 4) if total_reviewed else None,
            "rejected_rate": round(rejected_count / total_reviewed, 4) if total_reviewed else None,
            "false_positive_rate": round(false_positive_count / total_reviewed, 4) if total_reviewed else None,
            "false_negative_count": aggregate_outcomes.get("missed_opportunity", 0),
            "conversion_rate": round(total_converted / total_reviewed, 4) if total_reviewed else None,
        },
        "conversion": {
            "converted": total_converted,
            "next_steps": dict(sorted(aggregate_next_steps.items())),
        },
        "time_benchmark": {
            "manual_triage_minutes": total_manual if has_time else None,
            "tool_triage_minutes": total_tool if has_time else None,
            "time_saved_minutes": time_saved,
            "time_saved_pct": round((time_saved / total_manual) * 100, 2) if has_time and total_manual > 0 else None,
        },
        "entries": summaries,
    }


def summarize_readiness(validation_reports: list[ValidationReport]) -> dict:
    if not validation_reports:
        return {
            "grade": "F",
            "score": 0,
            "inputs": [],
            "remediation_actions": [],
        }
    worst_score = min(report.readiness_score for report in validation_reports)
    input_summaries = [
        {
            "kind": report.input_kind,
            "grade": report.readiness_grade,
            "score": report.readiness_score,
            "actions": len(report.remediation_actions),
        }
        for report in validation_reports
    ]
    actions = [
        {
            "kind": report.input_kind,
            **action.model_dump(mode="json"),
        }
        for report in validation_reports
        for action in report.remediation_actions
    ]
    data_requests = [
        {
            "kind": report.input_kind,
            **request.model_dump(mode="json"),
        }
        for report in validation_reports
        for request in report.data_request_checklist
    ]
    severity_order = {"error": 0, "warning": 1, "info": 2}
    actions = sorted(
        actions,
        key=lambda item: (
            severity_order.get(str(item.get("severity")), 9),
            str(item.get("field") or ""),
            str(item.get("action") or ""),
        ),
    )
    grade_order = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
    worst_grade = max(
        (report.readiness_grade for report in validation_reports),
        key=lambda grade: grade_order.get(grade, 99),
    )
    return {
        "grade": worst_grade,
        "score": worst_score,
        "inputs": input_summaries,
        "remediation_actions": actions,
        "data_request_checklist": data_requests,
        "source_window_findings": [
            {
                "kind": report.input_kind,
                "code": finding.code,
                "severity": finding.severity,
                "message": finding.message,
            }
            for report in validation_reports
            for finding in report.data_quality
            if finding.code in {"STALE_SOURCE_WINDOW", "SOURCE_WINDOW_SKEW"}
        ],
    }


def redact_validation_reports(
    validation_reports: list[ValidationReport],
    *,
    mode: PrivacyMode,
) -> list[ValidationReport]:
    redacted = [report.model_copy(deep=True) for report in validation_reports]
    if mode != "strict":
        return redacted
    for report in redacted:
        report.path = "<redacted>"
        report.warnings = ["<redacted>" for _ in report.warnings]
        for finding in report.data_quality:
            finding.message = "<redacted>"
            for source_ref in finding.source_refs:
                source_ref.path = "<redacted>"
        for profile in report.field_profiles:
            profile.sample_values = ["<redacted>" for _ in profile.sample_values]
        if report.mapping_approval.approved_by:
            report.mapping_approval.approved_by = "<redacted>"
        if report.mapping_approval.approval_notes:
            report.mapping_approval.approval_notes = "<redacted>"
    return redacted


def _adapter_for(kind: MappingKind):
    return {
        "inventory": read_inventory_evidence_csv,
        "backup": read_backup_evidence_csv,
        "utilization": read_utilization_evidence_csv,
    }[kind]


def _report_grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _parse_source_window(value: str) -> datetime | None:
    warnings: list[str] = []
    end_value = value.split("/", 1)[-1].strip() if "/" in value else value.strip()
    parsed = parse_datetime(end_value, field="source_window", row_number=1, warnings=warnings)
    return parsed.astimezone(timezone.utc) if parsed is not None else None


def _append_readiness_finding(
    report: ValidationReport,
    finding: DataQualityFinding,
    *,
    action: str,
    reason: str,
) -> None:
    report.data_quality.append(finding)
    report.warnings.append(finding.message)
    report.business_severity_counts["medium"] = report.business_severity_counts.get("medium", 0) + 1
    report.readiness_score = max(0, report.readiness_score - (12 if finding.severity == "warning" else 25))
    report.readiness_grade = _report_grade(report.readiness_score)
    report.remediation_actions.append(
        ReadinessAction(
            severity=finding.severity,
            field=finding.field,
            action=action,
            reason=reason,
        )
    )


def _apply_source_window_quality(
    bundle_dir: Path,
    validation_reports: list[ValidationReport],
    *,
    stale_days: int = 30,
    skew_days: int = 7,
) -> None:
    metadata_path = bundle_dir / "source-metadata.yml"
    if not metadata_path.exists():
        return
    try:
        raw = yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return
    source_windows = raw.get("source_windows") or {}
    if not isinstance(source_windows, dict):
        return
    parsed_windows: dict[str, datetime] = {}
    for relative_path, raw_window in source_windows.items():
        if not isinstance(relative_path, str) or not isinstance(raw_window, str):
            continue
        parsed = _parse_source_window(raw_window)
        if parsed is not None:
            parsed_windows[relative_path] = parsed
    if not parsed_windows:
        return
    newest = max(parsed_windows.values())
    reports_by_relative_path = {
        str(Path(report.path).relative_to(bundle_dir)): report
        for report in validation_reports
        if Path(report.path).is_relative_to(bundle_dir)
    }
    for relative_path, observed_at in parsed_windows.items():
        age_days = (newest - observed_at).total_seconds() / 86400
        if age_days <= stale_days:
            continue
        report = reports_by_relative_path.get(relative_path)
        if report is None:
            continue
        finding = DataQualityFinding(
            code="STALE_SOURCE_WINDOW",
            severity="warning",
            message=(
                f"Input source window is {round(age_days, 1)} days older than the newest "
                "source in the bundle."
            ),
            source_refs=[
                SourceRef(
                    source_type=report.input_kind,  # type: ignore[arg-type]
                    path=report.path,
                )
            ],
        )
        _append_readiness_finding(
            report,
            finding,
            action="Refresh the stale export or confirm the date difference is intentional.",
            reason=f"STALE_SOURCE_WINDOW: {finding.message}",
        )
    if len(parsed_windows) <= 1:
        return
    oldest = min(parsed_windows.values())
    skew = (newest - oldest).total_seconds() / 86400
    if skew <= skew_days:
        return
    for relative_path, observed_at in parsed_windows.items():
        report = reports_by_relative_path.get(relative_path)
        if report is None:
            continue
        finding = DataQualityFinding(
            code="SOURCE_WINDOW_SKEW",
            severity="warning",
            message=(
                f"Bundle source windows span {round(skew, 1)} days; this input was captured "
                f"at {observed_at.isoformat()}."
            ),
            source_refs=[
                SourceRef(
                    source_type=report.input_kind,  # type: ignore[arg-type]
                    path=report.path,
                )
            ],
        )
        _append_readiness_finding(
            report,
            finding,
            action="Align export capture windows before presenting findings.",
            reason=f"SOURCE_WINDOW_SKEW: {finding.message}",
        )


def load_bundle_inputs(
    bundle_dir: Path,
    manifest: EstateBundleManifest,
    *,
    strict: bool,
) -> tuple[list[AdapterResult], list[ValidationReport], list[InputFingerprint]]:
    adapter_results: list[AdapterResult] = []
    validation_reports: list[ValidationReport] = []
    fingerprints: list[InputFingerprint] = []
    for input_spec in manifest.inputs:
        input_path = bundle_dir / input_spec.path
        mapping_path = bundle_dir / input_spec.mapping if input_spec.mapping else None
        mapping = load_column_mapping(mapping_path, kind=input_spec.kind)
        adapter = _adapter_for(input_spec.kind)
        result = adapter(input_path, strict=strict, mapping_spec=mapping)
        headers = headers_for(input_path)
        mapped_fields = list((mapping.columns if mapping else {}).keys())
        mapped_headers = list((mapping.columns if mapping else {}).values())
        if mapping is None:
            from estate_triage.mapping import inferred_mapping

            inferred = inferred_mapping(input_spec.kind, headers)
            mapped_fields = list(inferred.columns.keys())
            mapped_headers = list(inferred.columns.values())
        validation_reports.append(
            validation_report(
                input_kind=input_spec.kind,
                path=input_path,
                adapter_result=result,
                mapped_fields=mapped_fields,
                headers=headers,
                mapped_headers=mapped_headers,
                mapping_approval=MappingApproval(
                    approved=bool(mapping and mapping.approved_by),
                    approved_by=mapping.approved_by if mapping else None,
                    approved_at_utc=mapping.approved_at_utc if mapping else None,
                    approval_notes=mapping.approval_notes if mapping else None,
                ),
            )
        )
        adapter_results.append(result)
        fingerprints.append(fingerprint_csv(input_path))
    _apply_source_window_quality(bundle_dir, validation_reports)
    return adapter_results, validation_reports, fingerprints


def summary_for_assessment(
    *,
    assessment: AssessmentResult,
    rows_written: int,
    top_n: int,
    ranking_mode: RankingMode,
    validation_reports: list[ValidationReport] | None = None,
    feedback_summary: dict | None = None,
) -> dict:
    motions = {
        "MIGRATION_REVIEW": 0,
        "ARCHIVE_REVIEW": 0,
        "RIGHTSIZING_REVIEW": 0,
        "DR_TIER_REVIEW": 0,
    }
    for workload in assessment.workloads:
        motions[workload.winning_motion.motion] += 1
    return {
        "input": {
            "inventory_rows": assessment.input.get("inventory_rows", 0),
            "backup_rows": assessment.input.get("backup_rows", 0),
            "utilization_rows": assessment.input.get("utilization_rows", 0),
            "matched_by_uuid": assessment.input.get("matched_by_uuid", 0),
            "matched_by_name": assessment.input.get("matched_by_name", 0),
            "unmatched_inventory": assessment.input.get("unmatched_inventory", 0),
        },
        "output": {
            "top_n": top_n,
            "rows_written": rows_written,
            "ranking_mode": ranking_mode.value,
        },
        "motions": motions,
        "schemas": {
            "assessment": assessment.schema_version,
            "trace": assessment.trace_schema_version,
            "policy": assessment.policy_version,
        },
        "data_quality": {
            "findings": len(assessment.data_quality)
            + sum(len(workload.data_quality) for workload in assessment.workloads),
        },
        "readiness": summarize_readiness(validation_reports or []),
        "business_impact": workflow_summary(assessment),
        "feedback": feedback_summary or {"items": 0, "outcomes": {}},
        "warnings": assessment.warnings,
    }


def analyze_bundle(
    bundle_dir: Path,
    *,
    strict: bool = False,
    top_n: int | None = None,
    ranking_mode: RankingMode = RankingMode.BALANCED,
    redact: bool = True,
) -> BundleRunResult:
    manifest = load_manifest(bundle_dir)
    adapter_results, validation_reports, fingerprints = load_bundle_inputs(
        bundle_dir,
        manifest,
        strict=strict,
    )
    thresholds = load_thresholds(
        bundle_dir / manifest.policy.thresholds if manifest.policy.thresholds else None
    )
    policy_pack = load_policy_pack(
        bundle_dir / manifest.policy.policy_pack if manifest.policy.policy_pack else None
    )
    assessment = analyze_estate(
        evidence_sources=[result.evidence for result in adapter_results],
        thresholds=thresholds,
        policy_pack=policy_pack,
        identity_overrides=load_identity_overrides(
            bundle_dir / manifest.identity_overrides if manifest.identity_overrides else None
        ),
        warnings=[warning for result in adapter_results for warning in result.warnings],
    )
    effective_top_n = top_n or thresholds.top_n
    ranked = rank_assessments(assessment, top_n=effective_top_n, mode=ranking_mode)
    feedback_summary = summarize_feedback(_read_feedback(bundle_dir, manifest))
    summary = summary_for_assessment(
        assessment=assessment,
        rows_written=len(ranked),
        top_n=effective_top_n,
        ranking_mode=ranking_mode,
        validation_reports=validation_reports,
        feedback_summary=feedback_summary,
    )

    out_dir = bundle_dir / manifest.outputs.directory
    write_results_csv(out_dir / manifest.outputs.top_csv, ranked, redact=redact)
    write_summary_json(out_dir / manifest.outputs.summary_json, summary)
    write_assessment_json(
        out_dir / manifest.outputs.assessment_json,
        assessment,
        redact=redact,
        salt=_salt(bundle_dir, manifest.privacy),
        privacy_mode=manifest.privacy.redaction_mode,
    )
    write_fingerprints(out_dir / manifest.outputs.fingerprints_json, fingerprints)
    output_validation_reports = (
        redact_validation_reports(validation_reports, mode=manifest.privacy.redaction_mode)
        if redact
        else validation_reports
    )
    (out_dir / manifest.outputs.validation_json).write_text(
        json.dumps([report.model_dump(mode="json") for report in output_validation_reports], indent=2)
        + "\n",
        encoding="utf-8",
    )
    return BundleRunResult(
        assessment=assessment,
        summary=summary,
        validation_reports=validation_reports,
        fingerprints=fingerprints,
        feedback_summary=feedback_summary,
    )


def write_feedback_template(path: Path, *, assessment_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    template = FeedbackFile(
        assessment_id=assessment_id,
        manual_triage_minutes=None,
        tool_triage_minutes=None,
        feedback=[
            FeedbackItem(
                workload_key="example-hash",
                finding="DR_TIER_REVIEW",
                outcome="accepted",
                converted=True,
                next_step="deeper_assessment",
                notes="replace with reviewed local feedback",
            )
        ],
    )
    path.write_text(yaml.safe_dump(template.model_dump(mode="json"), sort_keys=False), encoding="utf-8")
