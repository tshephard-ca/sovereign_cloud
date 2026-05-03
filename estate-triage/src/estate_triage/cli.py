"""Command-line interface for estate-triage."""

from __future__ import annotations

import csv
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

import typer

from estate_triage.adapters import (
    merge_evidence_sets,
    read_backup_evidence_csv,
    read_inventory_evidence_csv,
    read_utilization_evidence_csv,
)
from estate_triage.api import analyze_csv_estate
from estate_triage.assessment import RankingMode, rank_assessments
from estate_triage.bundle import (
    FeedbackFile,
    analyze_bundle as run_bundle_analysis,
    load_manifest,
    summarize_feedback,
    summarize_feedback_ledger,
    write_feedback_template,
)
from estate_triage.compare import compare_assessments
from estate_triage.columns import BACKUP_ALIASES, INVENTORY_ALIASES, identify_columns
from estate_triage.config import load_thresholds
from estate_triage.corpus import (
    sanitize_bundle_to_corpus,
    test_policy_against_corpus,
    validate_sanitized_corpus,
)
from estate_triage.evidence import (
    ASSESSMENT_SCHEMA_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    FEATURE_SCHEMA_VERSION,
    POLICY_SCHEMA_VERSION,
    TRACE_SCHEMA_VERSION,
    EvidenceSet,
)
from estate_triage.identity import (
    IdentityOverrideSet,
    identity_graph_payload,
    load_identity_overrides,
    resolve_identities,
)
from estate_triage.fingerprint import fingerprint_csv, write_fingerprints
from estate_triage.mapping import MappingKind, headers_for, load_column_mapping, write_initial_mapping
from estate_triage.models import TriageError
from estate_triage.policy import DEFAULT_POLICY_PACK, PolicyPack, load_policy_pack
from estate_triage.policy_impact import policy_change_impact
from estate_triage.privacy import redact_assessment
from estate_triage.real_world_generator import (
    EstateGeneratorProfile,
    derive_generator_profile_from_assessment,
    generate_real_world_bundle,
    load_generator_profile,
    validate_generator_profile,
    write_generator_profile,
)
from estate_triage.report import write_assessment_json, write_results_csv, write_summary_json
from estate_triage.assessment import AssessmentResult
from estate_triage.validation import MappingApproval, validation_report, write_validation_report
from estate_triage.workflow import workflow_summary, write_workflow_pack


app = typer.Typer(
    no_args_is_help=True,
    help="Deterministic estate triage CLI for review queues, data requests, and workflow handoff.",
)


@app.callback()
def main() -> None:
    """Deterministic estate triage CLI."""


def run_analysis(
    *,
    inventory_path: Path,
    backup_path: Path,
    utilization_path: Path | None = None,
    output_path: Path,
    config_path: Path | None = None,
    policy_path: Path | None = None,
    summary_path: Path | None = None,
    assessment_json_path: Path | None = None,
    top_n_override: int | None = None,
    strict: bool = False,
    redact: bool = False,
    ranking_mode: RankingMode = RankingMode.BALANCED,
    identity_overrides_path: Path | None = None,
    now: datetime | None = None,
) -> dict:
    thresholds = load_thresholds(config_path)
    policy_pack = load_policy_pack(policy_path)
    top_n = top_n_override if top_n_override is not None else thresholds.top_n
    if top_n < 1:
        raise TriageError("--top-n must be at least 1.")

    assessment = analyze_csv_estate(
        inventory_path=inventory_path,
        backup_path=backup_path,
        utilization_path=utilization_path,
        config_path=config_path,
        strict=strict,
        now=now,
        policy_pack=policy_pack,
        identity_overrides_path=identity_overrides_path,
    )
    ranked = rank_assessments(assessment, top_n=top_n, mode=ranking_mode)
    write_results_csv(output_path, ranked, redact=redact)
    if assessment_json_path is not None:
        write_assessment_json(assessment_json_path, assessment, redact=redact)

    motions = {
        "MIGRATION_REVIEW": 0,
        "ARCHIVE_REVIEW": 0,
        "RIGHTSIZING_REVIEW": 0,
        "DR_TIER_REVIEW": 0,
    }
    ranked_motions = dict(motions)
    for workload in assessment.workloads:
        motions[workload.winning_motion.motion] += 1
    for result in ranked:
        ranked_motions[result.primary_motion] += 1

    summary = {
        "input": {
            "inventory_rows": assessment.input["inventory_rows"],
            "backup_rows": assessment.input["backup_rows"],
            "utilization_rows": assessment.input.get("utilization_rows", 0),
            "matched_by_uuid": assessment.input["matched_by_uuid"],
            "matched_by_name": assessment.input["matched_by_name"],
            "unmatched_inventory": assessment.input["unmatched_inventory"],
        },
        "output": {
            "top_n": top_n,
            "rows_written": len(ranked),
            "ranking_mode": ranking_mode.value,
        },
        "motions": motions,
        "ranked_motions": ranked_motions,
        "schemas": {
            "assessment": assessment.schema_version,
            "trace": assessment.trace_schema_version,
            "policy": assessment.policy_version,
        },
        "data_quality": {
            "findings": len(assessment.data_quality)
            + sum(len(workload.data_quality) for workload in assessment.workloads),
        },
        "business_impact": workflow_summary(assessment),
        "warnings": assessment.warnings,
    }

    if summary_path is not None:
        write_summary_json(summary_path, summary)
    return summary


@app.command()
def analyze(
    inventory: Path = typer.Option(
        ...,
        "--inventory",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Virtual-infrastructure inventory CSV.",
    ),
    backup: Path = typer.Option(
        ...,
        "--backup",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Normalized backup metadata CSV.",
    ),
    utilization: Path | None = typer.Option(
        None,
        "--utilization",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Optional normalized utilization CSV.",
    ),
    output: Path = typer.Option(..., "--output", help="Output ranked CSV path."),
    top_n: int | None = typer.Option(None, "--top-n", min=1, help="Number of rows to write."),
    config: Path | None = typer.Option(
        None,
        "--config",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Threshold YAML file.",
    ),
    policy: Path | None = typer.Option(
        None,
        "--policy",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Optional local policy-pack YAML file.",
    ),
    identity_overrides: Path | None = typer.Option(
        None,
        "--identity-overrides",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Optional identity override YAML for known renames or source mismatches.",
    ),
    summary: Path | None = typer.Option(None, "--summary", help="Optional summary JSON path."),
    assessment_json: Path | None = typer.Option(
        None,
        "--assessment-json",
        help="Optional structured assessment JSON path with traces.",
    ),
    ranking_mode: RankingMode = typer.Option(
        RankingMode.BALANCED,
        "--ranking-mode",
        help="Ranking mode for selecting output rows.",
    ),
    strict: bool = typer.Option(False, "--strict", help="Fail on required schema problems."),
    redact: bool = typer.Option(False, "--redact", help="Redact workload names and keys in output."),
) -> None:
    try:
        result = run_analysis(
            inventory_path=inventory,
            backup_path=backup,
            utilization_path=utilization,
            output_path=output,
            config_path=config,
            policy_path=policy,
            summary_path=summary,
            assessment_json_path=assessment_json,
            top_n_override=top_n,
            strict=strict,
            redact=redact,
            ranking_mode=ranking_mode,
            identity_overrides_path=identity_overrides,
        )
    except TriageError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    for warning in result["warnings"]:
        typer.echo(f"Warning: {warning}", err=True)
    typer.echo(f"Wrote {result['output']['rows_written']} rows to {output}")


@app.command()
def validate(
    input: Path = typer.Option(
        ...,
        "--input",
        exists=True,
        dir_okay=False,
        readable=True,
        help="CSV file to validate.",
    ),
    kind: str = typer.Option(..., "--kind", help="Input kind: inventory or backup."),
    mapping: Path | None = typer.Option(
        None,
        "--mapping",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Optional column-mapping YAML.",
    ),
    output_json: Path | None = typer.Option(None, "--output-json", help="Optional validation JSON."),
    strict: bool = typer.Option(False, "--strict", help="Fail on required schema problems."),
) -> None:
    try:
        if kind not in {"inventory", "backup", "utilization"}:
            raise TriageError("--kind must be inventory, backup, or utilization.")
        mapping_spec = load_column_mapping(mapping, kind=kind) if mapping else None  # type: ignore[arg-type]
        if kind == "inventory":
            result = read_inventory_evidence_csv(input, strict=strict, mapping_spec=mapping_spec)
        elif kind == "backup":
            result = read_backup_evidence_csv(input, strict=strict, mapping_spec=mapping_spec)
        elif kind == "utilization":
            result = read_utilization_evidence_csv(input, strict=strict, mapping_spec=mapping_spec)
        else:
            raise TriageError("--kind must be inventory, backup, or utilization.")
    except TriageError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    headers = headers_for(input)
    mapped_fields = list(mapping_spec.columns.keys()) if mapping_spec else []
    mapped_headers = list(mapping_spec.columns.values()) if mapping_spec else []
    if mapping_spec is None:
        from estate_triage.mapping import inferred_mapping

        inferred = inferred_mapping(kind, headers)  # type: ignore[arg-type]
        mapped_fields = list(inferred.columns.keys())
        mapped_headers = list(inferred.columns.values())
    report = validation_report(
        input_kind=kind,
        path=input,
        adapter_result=result,
        mapped_fields=mapped_fields,
        headers=headers,
        mapped_headers=mapped_headers,
        mapping_approval=MappingApproval(
            approved=bool(mapping_spec and mapping_spec.approved_by),
            approved_by=mapping_spec.approved_by if mapping_spec else None,
            approved_at_utc=mapping_spec.approved_at_utc if mapping_spec else None,
            approval_notes=mapping_spec.approval_notes if mapping_spec else None,
        ),
    )
    if output_json is not None:
        write_validation_report(output_json, report)
    finding_count = len(result.evidence.data_quality) + sum(
        len(record.data_quality) for record in result.evidence.records
    )
    for warning in result.warnings:
        typer.echo(f"Warning: {warning}", err=True)
    typer.echo(
        f"Validated {result.row_count} {kind} rows; "
        f"recognized {len(result.evidence.records)} records; "
        f"data quality findings: {finding_count}; "
        f"readiness: {report.readiness_grade} ({report.readiness_score})"
    )


@app.command("inspect-schema")
def inspect_schema(
    input: Path = typer.Option(
        ...,
        "--input",
        exists=True,
        dir_okay=False,
        readable=True,
        help="CSV file to inspect.",
    ),
) -> None:
    try:
        with input.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            headers = reader.fieldnames or []
    except UnicodeDecodeError as exc:
        typer.echo(f"Error: {input} is not valid UTF-8: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except csv.Error as exc:
        typer.echo(f"Error: could not parse {input}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except OSError as exc:
        typer.echo(f"Error: could not read {input}: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    inventory = identify_columns(headers, INVENTORY_ALIASES)
    backup = identify_columns(headers, BACKUP_ALIASES)
    from estate_triage.columns import UTILIZATION_ALIASES

    utilization = identify_columns(headers, UTILIZATION_ALIASES)
    typer.echo("headers:")
    for header in headers:
        typer.echo(f"- {header}")
    typer.echo("inventory_aliases:")
    for canonical, header in sorted(inventory.items()):
        typer.echo(f"- {canonical}: {header}")
    typer.echo("backup_aliases:")
    for canonical, header in sorted(backup.items()):
        typer.echo(f"- {canonical}: {header}")
    typer.echo("utilization_aliases:")
    for canonical, header in sorted(utilization.items()):
        typer.echo(f"- {canonical}: {header}")


@app.command("identity-graph")
def identity_graph(
    inventory: Path = typer.Option(..., "--inventory", exists=True, dir_okay=False, readable=True),
    backup: Path = typer.Option(..., "--backup", exists=True, dir_okay=False, readable=True),
    output: Path = typer.Option(..., "--output", help="Identity graph JSON output."),
    utilization: Path | None = typer.Option(
        None,
        "--utilization",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    identity_overrides: Path | None = typer.Option(
        None,
        "--identity-overrides",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    strict: bool = typer.Option(False, "--strict"),
) -> None:
    try:
        inventory_result = read_inventory_evidence_csv(inventory, strict=strict)
        backup_result = read_backup_evidence_csv(backup, strict=strict)
        evidence_sets = [inventory_result.evidence, backup_result.evidence]
        if utilization is not None:
            evidence_sets.append(read_utilization_evidence_csv(utilization, strict=strict).evidence)
        identity = resolve_identities(
            merge_evidence_sets(*evidence_sets),
            overrides=load_identity_overrides(identity_overrides),
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(identity_graph_payload(identity), indent=2) + "\n",
            encoding="utf-8",
        )
    except TriageError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Wrote identity graph to {output}")


@app.command()
def schema(
    kind: str = typer.Option(
        ...,
        "--kind",
        help="Schema kind: evidence, assessment, policy, bundle, generator-profile, identity-overrides, or compatibility.",
    ),
) -> None:
    if kind == "evidence":
        payload = EvidenceSet.model_json_schema()
    elif kind == "assessment":
        payload = AssessmentResult.model_json_schema()
    elif kind == "policy":
        payload = PolicyPack.model_json_schema()
    elif kind == "bundle":
        from estate_triage.bundle import EstateBundleManifest

        payload = EstateBundleManifest.model_json_schema()
    elif kind == "generator-profile":
        payload = EstateGeneratorProfile.model_json_schema()
    elif kind == "identity-overrides":
        payload = IdentityOverrideSet.model_json_schema()
    elif kind == "compatibility":
        payload = {
            "schema_versions": {
                "evidence": EVIDENCE_SCHEMA_VERSION,
                "feature": FEATURE_SCHEMA_VERSION,
                "policy": POLICY_SCHEMA_VERSION,
                "assessment": ASSESSMENT_SCHEMA_VERSION,
                "trace": TRACE_SCHEMA_VERSION,
            },
            "default_policy": {
                "id": DEFAULT_POLICY_PACK.id,
                "version": DEFAULT_POLICY_PACK.version,
                "compatible_schema_versions": DEFAULT_POLICY_PACK.compatible_schema_versions,
            },
        }
    else:
        typer.echo(
            "Error: --kind must be evidence, assessment, policy, bundle, generator-profile, identity-overrides, or compatibility.",
            err=True,
        )
        raise typer.Exit(code=1)
    typer.echo(json.dumps(payload, indent=2, sort_keys=True))


@app.command("init-mapping")
def init_mapping(
    kind: str = typer.Option(..., "--kind", help="Input kind: inventory, backup, or utilization."),
    input: Path = typer.Option(..., "--input", exists=True, dir_okay=False, readable=True),
    output: Path = typer.Option(..., "--output", help="Mapping YAML output."),
) -> None:
    if kind not in {"inventory", "backup", "utilization"}:
        typer.echo("Error: --kind must be inventory, backup, or utilization.", err=True)
        raise typer.Exit(code=1)
    mapping = write_initial_mapping(kind=kind, input_path=input, output_path=output)  # type: ignore[arg-type]
    typer.echo(f"Wrote {mapping.source_kind} mapping with {len(mapping.columns)} columns to {output}")


@app.command("analyze-bundle")
def analyze_bundle_command(
    bundle: Path = typer.Argument(..., exists=True, file_okay=False, readable=True),
    top_n: int | None = typer.Option(None, "--top-n", min=1),
    ranking_mode: RankingMode = typer.Option(RankingMode.BALANCED, "--ranking-mode"),
    strict: bool = typer.Option(False, "--strict"),
    no_redact: bool = typer.Option(False, "--no-redact", help="Write unredacted bundle outputs."),
) -> None:
    try:
        result = run_bundle_analysis(
            bundle,
            strict=strict,
            top_n=top_n,
            ranking_mode=ranking_mode,
            redact=not no_redact,
        )
    except TriageError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        f"Analyzed bundle {bundle}; wrote {result.summary['output']['rows_written']} ranked rows."
    )


@app.command("fingerprint")
def fingerprint_command(
    input: list[Path] = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    output: Path = typer.Option(..., "--output", help="Fingerprint JSON output."),
) -> None:
    fingerprints = [fingerprint_csv(path) for path in input]
    write_fingerprints(output, fingerprints)
    typer.echo(f"Wrote fingerprints for {len(fingerprints)} inputs to {output}")


@app.command("feedback-template")
def feedback_template(
    output: Path = typer.Option(..., "--output", help="Feedback YAML output."),
    assessment_id: str = typer.Option("local-assessment-001", "--assessment-id"),
) -> None:
    write_feedback_template(output, assessment_id=assessment_id)
    typer.echo(f"Wrote feedback template to {output}")


@app.command("feedback-summary")
def feedback_summary(
    feedback: Path = typer.Option(..., "--feedback", exists=True, dir_okay=False, readable=True),
) -> None:
    try:
        import yaml

        raw = yaml.safe_load(feedback.read_text(encoding="utf-8")) or {}
        feedback_file = FeedbackFile(**raw)
    except Exception as exc:
        typer.echo(f"Error: invalid feedback file {feedback}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(summarize_feedback(feedback_file), indent=2))


@app.command("outcome-ledger")
def outcome_ledger(
    feedback: list[Path] = typer.Argument(..., exists=True, dir_okay=False, readable=True),
) -> None:
    try:
        import yaml

        feedback_files = [
            FeedbackFile(**(yaml.safe_load(path.read_text(encoding="utf-8")) or {}))
            for path in feedback
        ]
    except Exception as exc:
        typer.echo(f"Error: invalid feedback file: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(summarize_feedback_ledger(feedback_files), indent=2))


@app.command("compare-assessments")
def compare_assessments_command(
    baseline: Path = typer.Option(..., "--baseline", exists=True, dir_okay=False, readable=True),
    current: Path = typer.Option(..., "--current", exists=True, dir_okay=False, readable=True),
) -> None:
    try:
        comparison = compare_assessments(baseline, current)
    except TriageError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(comparison.model_dump(mode="json"), indent=2))


@app.command("policy-impact")
def policy_impact(
    assessment_json: Path = typer.Option(
        ...,
        "--assessment-json",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    candidate_policy: Path = typer.Option(
        ...,
        "--candidate-policy",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    baseline_policy: Path | None = typer.Option(
        None,
        "--baseline-policy",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
) -> None:
    try:
        assessment = AssessmentResult.model_validate_json(assessment_json.read_text(encoding="utf-8"))
        report = policy_change_impact(
            assessment,
            baseline_policy=load_policy_pack(baseline_policy),
            candidate_policy=load_policy_pack(candidate_policy),
            thresholds=load_thresholds(config),
        )
    except TriageError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(report.model_dump(mode="json"), indent=2))


@app.command("workflow-pack")
def workflow_pack(
    assessment_json: Path = typer.Option(
        ...,
        "--assessment-json",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    output_dir: Path = typer.Option(..., "--output-dir", help="Workflow pack output directory."),
    top_n: int = typer.Option(25, "--top-n", min=1),
) -> None:
    try:
        assessment = AssessmentResult.model_validate_json(assessment_json.read_text(encoding="utf-8"))
        write_workflow_pack(assessment, output_dir, top_n=top_n)
    except TriageError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Wrote workflow pack to {output_dir}")


@app.command("run-workflow")
def run_workflow(
    bundle: Path = typer.Argument(..., exists=True, file_okay=False, readable=True),
    top_n: int | None = typer.Option(None, "--top-n", min=1),
    ranking_mode: RankingMode = typer.Option(RankingMode.BALANCED, "--ranking-mode"),
    strict: bool = typer.Option(False, "--strict"),
) -> None:
    try:
        result = run_bundle_analysis(
            bundle,
            strict=strict,
            top_n=top_n,
            ranking_mode=ranking_mode,
            redact=True,
        )
        manifest = load_manifest(bundle)
        workflow_dir = bundle / manifest.outputs.directory / "workflow"
        salt = ""
        if manifest.privacy.hash_salt_file is not None:
            salt_path = bundle / manifest.privacy.hash_salt_file
            if salt_path.exists():
                salt = salt_path.read_text(encoding="utf-8")
        workflow_assessment = redact_assessment(
            result.assessment,
            salt=salt,
            mode=manifest.privacy.redaction_mode,
        )
        write_workflow_pack(
            workflow_assessment,
            workflow_dir,
            top_n=top_n or result.summary["output"]["top_n"],
        )
    except TriageError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Analyzed bundle and wrote workflow artifacts to {workflow_dir}")


@app.command("missing-evidence")
def missing_evidence(
    assessment_json: Path = typer.Option(..., "--assessment-json", exists=True, dir_okay=False, readable=True),
) -> None:
    assessment = AssessmentResult.model_validate_json(assessment_json.read_text(encoding="utf-8"))
    counts: dict[str, dict[str, int]] = {}
    for workload in assessment.workloads:
        for request in workload.missing_evidence:
            field_counts = counts.setdefault(request.field, {"high": 0, "medium": 0})
            field_counts[request.priority] = field_counts.get(request.priority, 0) + 1
    ordered = dict(
        sorted(
            counts.items(),
            key=lambda item: (-(item[1].get("high", 0) * 2 + item[1].get("medium", 0)), item[0]),
        )
    )
    typer.echo(json.dumps({"missing_evidence": ordered}, indent=2))


@app.command("preview-top-findings")
def preview_top_findings(
    assessment_json: Path = typer.Option(..., "--assessment-json", exists=True, dir_okay=False, readable=True),
    top_n: int = typer.Option(10, "--top-n", min=1),
    ranking_mode: RankingMode = typer.Option(RankingMode.BALANCED, "--ranking-mode"),
) -> None:
    assessment = AssessmentResult.model_validate_json(assessment_json.read_text(encoding="utf-8"))
    ranked = rank_assessments(assessment, top_n=top_n, mode=ranking_mode)
    typer.echo(
        json.dumps(
            [
                {
                    "rank": row.rank,
                    "workload_key": row.workload_key,
                    "motion": row.primary_motion,
                    "score": row.opportunity_score,
                    "confidence": row.confidence,
                    "reason_codes": row.reason_codes,
                    "blocking_flags": row.blocking_flags,
                }
                for row in ranked
            ],
            indent=2,
        )
    )


@app.command("explain-workload")
def explain_workload(
    assessment_json: Path = typer.Option(..., "--assessment-json", exists=True, dir_okay=False, readable=True),
    workload_key: str = typer.Option(..., "--workload-key"),
) -> None:
    assessment = AssessmentResult.model_validate_json(assessment_json.read_text(encoding="utf-8"))
    workload = next(
        (
            item
            for item in assessment.workloads
            if item.workload_key == workload_key or item.workload_id == workload_key
        ),
        None,
    )
    if workload is None:
        typer.echo(f"Error: workload not found: {workload_key}", err=True)
        raise typer.Exit(code=1)
    typer.echo(
        json.dumps(
            {
                "workload_key": workload.workload_key,
                "workload_name": workload.workload_name,
                "identity": workload.identity.trace.model_dump(mode="json"),
                "confidence": workload.confidence,
                "confidence_factors": workload.confidence_factors,
                "winning_motion": workload.winning_motion.model_dump(mode="json"),
                "blocking_flags": [detail.model_dump(mode="json") for detail in workload.blocking_flag_details],
                "missing_evidence": [request.model_dump(mode="json") for request in workload.missing_evidence],
                "features": {
                    name: feature.model_dump(mode="json")
                    for name, feature in workload.feature_set.features.items()
                },
            },
            indent=2,
        )
    )


@app.command("describe-thresholds")
def describe_thresholds(
    config: Path | None = typer.Option(None, "--config", exists=True, dir_okay=False, readable=True),
) -> None:
    thresholds = load_thresholds(config)
    descriptions = {
        "recent_backup_days": "Restore point age considered recent.",
        "stale_backup_days": "Restore point or inventory recency age considered stale.",
        "high_cpu_count": "Allocated CPU count that triggers allocation review.",
        "high_memory_mib": "Allocated memory that triggers allocation review.",
        "small_workload_mib": "Storage-used threshold for small-footprint review.",
        "large_backup_mib": "Backup-size threshold for large-footprint review.",
        "low_change_rate_pct": "Daily change-rate percentage considered low.",
        "high_backup_to_used_ratio": "Backup-to-used ratio considered high.",
        "many_restore_points": "Restore-point count considered high.",
        "idle_cpu_pct": "CPU utilization threshold for idle CPU review.",
        "low_memory_usage_pct": "Memory utilization threshold for oversized-memory review.",
    }
    typer.echo(
        json.dumps(
            {
                field: {
                    "value": getattr(thresholds, field),
                    "description": description,
                }
                for field, description in descriptions.items()
            },
            indent=2,
        )
    )


@app.command("handoff-bundle")
def handoff_bundle(
    source_dir: Path = typer.Option(..., "--source-dir", exists=True, file_okay=False, readable=True),
    output: Path = typer.Option(..., "--output", help="ZIP output path."),
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir))
    typer.echo(f"Wrote handoff bundle to {output}")


@app.command("privacy-scan")
def privacy_scan(
    path: Path = typer.Option(..., "--path", exists=True, readable=True),
    needle: list[str] = typer.Option([], "--needle", help="Literal string that must not appear."),
    output_json: Path | None = typer.Option(None, "--output-json"),
) -> None:
    files = [path] if path.is_file() else [item for item in path.rglob("*") if item.is_file()]
    secret_patterns = {
        "SECRET_ASSIGNMENT": re.compile(r"(?i)(password|secret|api[_-]?key|token)\s*[:=]\s*['\"]?[^'\"\s]+"),
        "PRIVATE_KEY": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    }
    findings: list[dict[str, str | int]] = []
    for file_path in files:
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for literal in needle:
            if literal and literal in text:
                findings.append(
                    {
                        "path": str(file_path),
                        "kind": "NEEDLE",
                        "value": literal,
                    }
                )
        for kind, pattern in secret_patterns.items():
            for match in pattern.finditer(text):
                findings.append(
                    {
                        "path": str(file_path),
                        "kind": kind,
                        "line": text.count("\n", 0, match.start()) + 1,
                    }
                )
    payload = {"files_scanned": len(files), "findings": findings}
    if output_json is not None:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    typer.echo(json.dumps(payload, indent=2))
    if findings:
        raise typer.Exit(code=1)


@app.command("sanitize-corpus")
def sanitize_corpus(
    bundle: Path = typer.Option(..., "--bundle", exists=True, file_okay=False, readable=True),
    output: Path = typer.Option(..., "--output", help="Corpus case output directory."),
) -> None:
    try:
        sanitize_bundle_to_corpus(bundle, output)
    except TriageError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Wrote sanitized corpus case to {output}")


@app.command("test-policy")
def test_policy(
    policy: Path = typer.Option(..., "--policy", exists=True, dir_okay=False, readable=True),
    corpus: Path = typer.Option(..., "--corpus", exists=True, file_okay=False, readable=True),
) -> None:
    try:
        result = test_policy_against_corpus(policy, corpus)
    except TriageError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(result, indent=2))
    if result["status"] != "passed":
        raise typer.Exit(code=1)


@app.command("validate-corpus")
def validate_corpus(
    corpus: Path = typer.Option(..., "--corpus", exists=True, file_okay=False, readable=True),
) -> None:
    try:
        result = validate_sanitized_corpus(corpus)
    except TriageError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    if result.status != "passed":
        raise typer.Exit(code=1)


@app.command("generate-real-world-data")
def generate_real_world_data(
    output: Path = typer.Option(..., "--output", help="Output bundle directory."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing generated bundle."),
    profile: str = typer.Option(
        "coverage",
        "--profile",
        help="Built-in generator profile: coverage, smb, midmarket, or enterprise.",
    ),
    profile_config: Path | None = typer.Option(
        None,
        "--profile-config",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Optional custom EstateGeneratorProfile YAML. Overrides --profile.",
    ),
    multi_source: bool = typer.Option(
        False,
        "--multi-source",
        help="Generate split inventory and backup CSVs plus source-window metadata.",
    ),
    edge_cases: bool = typer.Option(
        False,
        "--edge-cases",
        help="Generate messy CSV fixtures for adapter and readiness validation.",
    ),
) -> None:
    try:
        summary = generate_real_world_bundle(
            output,
            overwrite=overwrite,
            profile_name=profile,
            profile_config=profile_config,
            multi_source=multi_source,
            edge_cases=edge_cases,
        )
    except TriageError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(summary.model_dump(), indent=2))


@app.command("validate-generator-profile")
def validate_generator_profile_command(
    profile_config: Path = typer.Option(
        ...,
        "--profile-config",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Generator profile YAML to validate.",
    ),
    require_field_derived: bool = typer.Option(
        False,
        "--require-field-derived",
        help="Fail unless the profile declares sanitized field-derived calibration.",
    ),
) -> None:
    try:
        profile = load_generator_profile(profile_config=profile_config)
        result = validate_generator_profile(
            profile,
            require_field_derived=require_field_derived,
        )
    except TriageError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(result.model_dump(mode="json"), indent=2))
    if result.errors:
        raise typer.Exit(code=1)


@app.command("derive-generator-profile")
def derive_generator_profile(
    output: Path = typer.Option(..., "--output", help="Generator profile YAML output."),
    bundle: Path | None = typer.Option(
        None,
        "--bundle",
        exists=True,
        file_okay=False,
        readable=True,
        help="Bundle containing an outputs/assessment.json artifact.",
    ),
    assessment_json: Path | None = typer.Option(
        None,
        "--assessment-json",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Assessment JSON artifact to derive from.",
    ),
    name: str = typer.Option("sanitized-field-profile", "--name"),
    source: str = typer.Option("sanitized-field-derived", "--source"),
    description: str = typer.Option(
        "Scenario mix derived from sanitized assessment evidence.",
        "--description",
    ),
    sanitization_method: str = typer.Option(
        ...,
        "--sanitization-method",
        help="How source assessment data was sanitized before profile derivation.",
    ),
    source_window: str | None = typer.Option(None, "--source-window"),
    require_field_derived: bool = typer.Option(
        True,
        "--require-field-derived/--no-require-field-derived",
        help="Require the derived profile to pass strict field-derived validation.",
    ),
) -> None:
    if (bundle is None) == (assessment_json is None):
        typer.echo("Error: provide exactly one of --bundle or --assessment-json.", err=True)
        raise typer.Exit(code=1)
    try:
        if bundle is not None:
            manifest = load_manifest(bundle)
            assessment_path = bundle / manifest.outputs.directory / manifest.outputs.assessment_json
        else:
            assessment_path = assessment_json
        if assessment_path is None or not assessment_path.exists():
            raise TriageError(f"Assessment JSON not found: {assessment_path}")
        assessment = AssessmentResult.model_validate_json(assessment_path.read_text(encoding="utf-8"))
        profile = derive_generator_profile_from_assessment(
            assessment,
            name=name,
            source=source,
            description=description,
            sanitization_method=sanitization_method,
            source_window=source_window,
        )
        validation = validate_generator_profile(
            profile,
            require_field_derived=require_field_derived,
        )
        if validation.errors:
            raise TriageError("; ".join(validation.errors))
        write_generator_profile(output, profile)
    except TriageError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(
        json.dumps(
            {
                "output": str(output),
                "profile": profile.model_dump(mode="json"),
                "validation": validation.model_dump(mode="json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    app()
