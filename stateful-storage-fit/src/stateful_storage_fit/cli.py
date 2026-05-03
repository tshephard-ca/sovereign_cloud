from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
import yaml

from .app_metadata import build_app_metadata
from .calibration import load_calibration_report
from .collector import collect_du_summary, collect_local_bundle
from .contracts import get_contract_schema
from .corpus import case_template, evaluate_corpus
from .engine import analyze_paths
from .full_coverage_lab import generate_full_coverage_lab
from .gap_closure_lab import generate_gap_closure_lab
from .governance import (
    audit_manifest,
    business_impact_summary,
    calibration_actions,
    chain_of_custody_record,
    coverage_plan,
    decision_diff,
    evidence_modes,
    evidence_repository_export,
    export_evidence_questions,
    attestation_template,
    followup_sla,
    handoff_bundle,
    owner_evidence_template,
    operating_model_template,
    path_purpose_template,
    proprietary_scan,
    quality_gate,
    real_world_evidence_contract,
    sign_audit_manifest,
    timestamp_attestation_template,
    trend_report,
    tool_preflight,
    validate_attestation,
    verify_audit_manifest_signature,
)
from .parse_extra import load_extra_evidence
from .portfolio import analyze_portfolio
from .redact import Redactor
from .report import write_fit_result, write_mount_report
from .validators import load_yaml_mapping, validate_decision, validate_input_realism
from .workflow import (
    add_impact,
    add_outcome,
    add_review,
    adjudicate_case,
    bundle_paths,
    compare_evaluations,
    corpus_coverage,
    corpus_summary,
    create_case_from_bundle,
    export_outcome_requests,
    outcome_backlog,
    storage_profile_snapshot,
    validate_bundle,
    validate_case,
)


app = typer.Typer(no_args_is_help=True, help="Check local VM storage observations against a storage profile.")


@app.callback()
def main() -> None:
    """Local-only storage fit preflight."""


def _missing_or_unreadable(path: Path | None) -> bool:
    return path is None or not path.exists() or not path.is_file()


def _strict_input_check(
    df: Path | None,
    mount: Path | None,
    storage_profile: Path | None,
) -> None:
    if _missing_or_unreadable(df):
        raise typer.BadParameter("--df is required and must point to a readable file in strict mode")
    if _missing_or_unreadable(mount):
        raise typer.BadParameter("--mount is required and must point to a readable file in strict mode")
    if _missing_or_unreadable(storage_profile):
        raise typer.BadParameter("--storage-profile is required and must point to a readable file in strict mode")


def _parse_optional_file(path: Path | None, parser, missing_name: str, parse_warnings: list[str]):
    if _missing_or_unreadable(path):
        return None, [missing_name]
    try:
        value, warnings = parser(path)
        parse_warnings.extend(warnings)
        if not value:
            return value, [missing_name]
        return value, []
    except OSError as exc:
        parse_warnings.append(f"{missing_name.upper()}_READ_FAILED:{exc}")
        return None, [missing_name]


def _parse_bool_text(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"true", "yes", "1", "y"}:
        return True
    if normalized in {"false", "no", "0", "n"}:
        return False
    raise typer.BadParameter(f"expected true or false, got {value!r}")


def _write_json(data: dict, output: Optional[Path]) -> None:
    payload = json.dumps(data, indent=2) + "\n"
    if output is None:
        print(payload, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")


@app.command()
def check(
    bundle: Optional[Path] = typer.Option(None, "--bundle", help="Evidence bundle directory produced by collect."),
    df: Optional[Path] = typer.Option(None, "--df", help="Path to df output."),
    mount: Optional[Path] = typer.Option(None, "--mount", help="Path to mount output."),
    fstab: Optional[Path] = typer.Option(None, "--fstab", help="Path to /etc/fstab content."),
    iostat: Optional[Path] = typer.Option(None, "--iostat", help="Path to iostat sample."),
    ps: Optional[Path] = typer.Option(None, "--ps", help="Path to process list."),
    storage_profile_path: Optional[Path] = typer.Option(
        None,
        "--storage-profile",
        help="Path to target storage profile YAML.",
    ),
    output: Optional[Path] = typer.Option(None, "--output", help="Write JSON result to this file."),
    mount_report: Optional[Path] = typer.Option(None, "--mount-report", help="Write candidate mount CSV."),
    redact: bool = typer.Option(False, "--redact", help="Redact process args and non-system paths in reports."),
    strict: bool = typer.Option(False, "--strict", help="Fail fast on required missing or invalid inputs."),
    data_path: Optional[list[str]] = typer.Option(None, "--data-path", help="Additional data mount path."),
    config: Optional[Path] = typer.Option(None, "--config", help="Threshold override YAML."),
    policy_pack: Optional[Path] = typer.Option(None, "--policy-pack", help="Optional offline policy pack YAML."),
    calibration: Optional[Path] = typer.Option(None, "--calibration", help="Optional corpus evaluation JSON used for conservative confidence calibration."),
    findmnt_json: Optional[Path] = typer.Option(None, "--findmnt-json", help="Optional findmnt --json output."),
    lsblk_json: Optional[Path] = typer.Option(None, "--lsblk-json", help="Optional lsblk --json output."),
    blkid: Optional[Path] = typer.Option(None, "--blkid", help="Optional blkid output."),
    pvs: Optional[Path] = typer.Option(None, "--pvs", help="Optional pvs output."),
    vgs: Optional[Path] = typer.Option(None, "--vgs", help="Optional vgs output."),
    lvs: Optional[Path] = typer.Option(None, "--lvs", help="Optional lvs output."),
    inode_df: Optional[Path] = typer.Option(None, "--inode-df", help="Optional df -Pi output."),
    du_summary: Optional[Path] = typer.Option(None, "--du-summary", help="Optional du summary output."),
    app_name: Optional[str] = typer.Option(None, "--app-name", help="Optional application or workload name for evidence records."),
    workload_family: Optional[str] = typer.Option(None, "--workload-family", help="Optional workload family label."),
    path_purpose: Optional[Path] = typer.Option(None, "--path-purpose", help="Optional YAML declaring path ownership and purpose."),
    output_format: str = typer.Option("json", "--format", help="Output format. Only json is supported."),
) -> None:
    if output_format != "json":
        raise typer.BadParameter("only --format json is supported")
    bundle_validation = None
    if bundle is not None:
        paths = bundle_paths(bundle)
        bundle_validation = validate_bundle(bundle)
        if strict and not bundle_validation["valid"]:
            raise typer.BadParameter(f"invalid evidence bundle: {bundle_validation['issues']}")
        df = df or paths["df"]
        mount = mount or paths["mount"]
        fstab = fstab or paths["fstab"]
        iostat = iostat or paths["iostat"]
        ps = ps or paths["ps"]
        findmnt_json = findmnt_json or paths["findmnt_json"]
        lsblk_json = lsblk_json or paths["lsblk_json"]
        blkid = blkid or paths["blkid"]
        pvs = pvs or paths["pvs"]
        vgs = vgs or paths["vgs"]
        lvs = lvs or paths["lvs"]
        inode_df = inode_df or paths["inode_df"]
        du_summary = du_summary or paths["du_summary"]
        path_purpose = path_purpose or paths["path_purpose"]
    try:
        app_metadata = build_app_metadata(
            app_name=app_name,
            workload_family=workload_family,
            path_purpose_file=path_purpose,
        )
        if not (app_name or workload_family or app_metadata.get("declared_data_paths")):
            app_metadata = None
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    extra_evidence, extra_warnings = load_extra_evidence(
        findmnt_json=findmnt_json,
        lsblk_json=lsblk_json,
        blkid=blkid,
        pvs=pvs,
        vgs=vgs,
        lvs=lvs,
        inode_df=inode_df,
        du_summary=du_summary,
    )
    if bundle_validation is not None:
        extra_evidence["bundle_validation"] = bundle_validation
    try:
        calibration_report = load_calibration_report(calibration)
        bundle = analyze_paths(
            df=df,
            mount=mount,
            fstab=fstab,
            iostat=iostat,
            ps=ps,
            storage_profile_path=storage_profile_path,
            config=config,
            policy_pack_path=policy_pack,
            data_paths=data_path or [],
            strict=strict,
            extra_evidence=extra_evidence,
            calibration_report=calibration_report,
            app_metadata=app_metadata,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    redactor = Redactor()
    result = bundle.result
    result.warnings.extend(warning for warning in extra_warnings if warning not in result.warnings)

    if redact:
        result.analysis = redactor.redact_analysis(result.analysis)
    report_candidates = redactor.redact_mounts(bundle.candidate_mounts) if redact else bundle.candidate_mounts
    write_fit_result(result, output)
    if mount_report is not None:
        write_mount_report(report_candidates, mount_report)

    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)


@app.command()
def collect(
    output_dir: Path = typer.Option(..., "--output-dir", help="Directory for local collected text outputs."),
    minimal: bool = typer.Option(False, "--minimal", help="Collect only the original MVP command set."),
    timeout_seconds: int = typer.Option(20, "--timeout-seconds", help="Per-command timeout."),
    redact_first: bool = typer.Option(False, "--redact-first", help="Redact process args and non-system paths before writing bundle files."),
    process_redaction_mode: str = typer.Option(
        "strict",
        "--process-redaction-mode",
        help="Process redaction mode for --redact-first: strict, balanced, or none.",
    ),
) -> None:
    """Run an explicit local-only collector and write a bundle of text outputs."""
    try:
        manifest = collect_local_bundle(
            output_dir,
            include_optional=not minimal,
            timeout_seconds=timeout_seconds,
            redact_first=redact_first,
            process_redaction_mode=process_redaction_mode,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    print(json.dumps(manifest, indent=2))


@app.command("collect-du")
def collect_du_command(
    bundle: Path = typer.Option(..., "--bundle", help="Evidence bundle directory to update."),
    data_path: list[str] = typer.Option(..., "--data-path", help="Path to measure with du -sb. Repeat for multiple paths."),
    timeout_seconds: int = typer.Option(30, "--timeout-seconds", help="Per-path du timeout."),
    redact_paths: bool = typer.Option(False, "--redact-paths", help="Redact paths in du-summary.txt while preserving absolute path shape."),
) -> None:
    """Collect explicit du summaries for user-declared data paths."""
    try:
        manifest = collect_du_summary(
            bundle,
            data_paths=data_path,
            timeout_seconds=timeout_seconds,
            redact_paths=redact_paths,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    print(json.dumps({"updated": str(bundle), "bundle_fingerprint": manifest.get("bundle_fingerprint")}, indent=2))


@app.command("validate-bundle")
def validate_bundle_command(
    bundle: Path = typer.Option(..., "--bundle", help="Evidence bundle directory."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write validation JSON to this file."),
) -> None:
    """Validate an evidence bundle manifest, checksums, and completeness."""
    data = validate_bundle(bundle)
    payload = json.dumps(data, indent=2) + "\n"
    if output is None:
        print(payload, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")


@app.command("schema")
def schema_command(
    name: Optional[str] = typer.Option(None, "--name", help="Contract schema name. Omit to list names."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write schema JSON to this file."),
) -> None:
    """Print a versioned data contract schema."""
    try:
        data = get_contract_schema(name)
    except KeyError as exc:
        raise typer.BadParameter(f"unknown schema name: {name}") from exc
    payload = json.dumps(data, indent=2) + "\n"
    if output is None:
        print(payload, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")


@app.command("profile-snapshot")
def profile_snapshot_command(
    storage_profile: Path = typer.Option(..., "--storage-profile", help="Storage profile YAML to fingerprint."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write snapshot JSON to this file."),
    origin: str = typer.Option("user_supplied", "--origin", help="Profile origin label."),
    owner_note: Optional[str] = typer.Option(None, "--owner-note", help="Optional owner/provenance note."),
    source_metadata: Optional[Path] = typer.Option(None, "--source-metadata", help="Optional YAML mapping with offline profile source metadata."),
) -> None:
    """Create an offline storage-profile provenance snapshot."""
    try:
        metadata = load_yaml_mapping(source_metadata) if source_metadata else None
        data = storage_profile_snapshot(
            storage_profile,
            origin=origin,
            owner_note=owner_note,
            source_metadata=metadata,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _write_json(data, output)


@app.command("validate-decision")
def validate_decision_command(
    decision: Path = typer.Option(..., "--decision", help="Fit JSON decision to validate."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write validation JSON to this file."),
) -> None:
    """Validate a fit decision for internal consistency and realism."""
    _write_json(validate_decision(decision), output)


@app.command("validate-input-realism")
def validate_input_realism_command(
    bundle: Path = typer.Option(..., "--bundle", help="Evidence bundle directory."),
    storage_profile: Optional[Path] = typer.Option(None, "--storage-profile", help="Optional storage profile used with the bundle."),
    path_purpose: Optional[Path] = typer.Option(None, "--path-purpose", help="Optional path-purpose YAML used with the bundle."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write validation JSON to this file."),
) -> None:
    """Validate whether an input bundle is realistic enough for business use."""
    data = validate_input_realism(bundle_dir=bundle, storage_profile=storage_profile, path_purpose=path_purpose)
    _write_json(data, output)


@app.command("tool-preflight")
def tool_preflight_command(
    output: Optional[Path] = typer.Option(None, "--output", help="Write preflight JSON to this file."),
) -> None:
    """Report which local collection tools are available before collecting evidence."""
    _write_json(tool_preflight(), output)


@app.command("evidence-modes")
def evidence_modes_command(
    output: Optional[Path] = typer.Option(None, "--output", help="Write evidence mode JSON to this file."),
) -> None:
    """Print the collection and validation levels used by the project."""
    _write_json(evidence_modes(), output)


@app.command("path-purpose-template")
def path_purpose_template_command(
    bundle: Path = typer.Option(..., "--bundle", help="Evidence bundle directory."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write path-purpose template YAML to this file."),
) -> None:
    """Generate an owner-confirmation path-purpose template from observed candidate mounts."""
    try:
        data = path_purpose_template(bundle)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    payload = yaml.safe_dump(data, sort_keys=False)
    if output is None:
        print(payload, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")


@app.command("quality-gate")
def quality_gate_command(
    input_realism: Optional[Path] = typer.Option(None, "--input-realism", help="Input realism report JSON."),
    decision_validation: Optional[Path] = typer.Option(None, "--decision-validation", help="Decision validation report JSON."),
    case_validation: Optional[Path] = typer.Option(None, "--case-validation", help="Case validation report JSON."),
    corpus_evaluation: Optional[Path] = typer.Option(None, "--corpus-evaluation", help="Corpus evaluation report JSON."),
    gate_config: Optional[Path] = typer.Option(None, "--gate-config", help="Optional gate policy YAML."),
    mode: str = typer.Option("business_review", "--mode", help="Gate mode: business_review, calibration, or release."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write gate JSON to this file."),
) -> None:
    """Apply a configurable quality gate across validation artifacts."""
    try:
        data = quality_gate(
            input_realism=input_realism,
            decision_validation=decision_validation,
            case_validation=case_validation,
            corpus_evaluation=corpus_evaluation,
            gate_config=gate_config,
            mode=mode,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _write_json(data, output)


@app.command("audit-manifest")
def audit_manifest_command(
    audit_dir: Path = typer.Option(..., "--audit-dir", help="Audit output directory."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write audit manifest JSON to this file."),
) -> None:
    """Create a tamper-evident checksum manifest for an audit directory."""
    _write_json(audit_manifest(audit_dir), output)


@app.command("evidence-repository-export")
def evidence_repository_export_command(
    audit_dir: Path = typer.Option(..., "--audit-dir", help="Audit directory to export as an offline evidence repository manifest."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write repository export JSON to this file."),
) -> None:
    """Create an offline evidence repository export manifest with lineage and checksum fields."""
    _write_json(evidence_repository_export(audit_dir), output)


@app.command("chain-of-custody")
def chain_of_custody_command(
    audit_dir: Path = typer.Option(..., "--audit-dir", help="Audit directory to summarize."),
    external_timestamp_reference: Optional[str] = typer.Option(None, "--external-timestamp-reference", help="Optional external timestamp or repository reference."),
    signer_id: Optional[str] = typer.Option(None, "--signer-id", help="Optional local signer identifier."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write chain-of-custody JSON to this file."),
) -> None:
    """Create a local chain-of-custody record for a handoff artifact."""
    _write_json(
        chain_of_custody_record(
            audit_dir,
            external_timestamp_reference=external_timestamp_reference,
            signer_id=signer_id,
        ),
        output,
    )


@app.command("sign-audit-manifest")
def sign_audit_manifest_command(
    manifest: Path = typer.Option(..., "--manifest", help="Audit manifest JSON to sign."),
    key_file: Path = typer.Option(..., "--key-file", help="Local HMAC key file."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write signature JSON to this file."),
) -> None:
    """Create a local HMAC signature for an audit manifest."""
    _write_json(sign_audit_manifest(manifest, key_file), output)


@app.command("verify-audit-signature")
def verify_audit_signature_command(
    signature: Path = typer.Option(..., "--signature", help="Signature JSON produced by sign-audit-manifest."),
    key_file: Path = typer.Option(..., "--key-file", help="Local HMAC key file."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write verification JSON to this file."),
) -> None:
    """Verify a local HMAC signature for an audit manifest."""
    _write_json(verify_audit_manifest_signature(signature, key_file), output)


@app.command("decision-diff")
def decision_diff_command(
    old: Path = typer.Option(..., "--old", help="Previous fit JSON."),
    new: Path = typer.Option(..., "--new", help="New fit JSON."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write decision diff JSON to this file."),
) -> None:
    """Explain field, reason-code, warning, and blocker changes between two decisions."""
    _write_json(decision_diff(old, new), output)


@app.command("evidence-questions")
def evidence_questions_command(
    decision: Path = typer.Option(..., "--decision", help="Fit JSON decision."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write evidence-question JSON to this file."),
) -> None:
    """Export structured follow-up questions from a REVIEW decision."""
    _write_json(export_evidence_questions(decision), output)


@app.command("owner-evidence-template")
def owner_evidence_template_command(
    bundle: Optional[Path] = typer.Option(None, "--bundle", help="Optional bundle used to seed candidate paths."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write owner-evidence YAML to this file."),
) -> None:
    """Generate an owner evidence template for timing, growth, lifecycle, consistency, and topology facts."""
    payload = yaml.safe_dump(owner_evidence_template(bundle), sort_keys=False)
    if output is None:
        print(payload, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")


@app.command("attestation-template")
def attestation_template_command(
    kind: str = typer.Option(..., "--kind", help="Attestation kind: profile, path_purpose, or business_impact."),
    subject: Optional[str] = typer.Option(None, "--subject", help="Optional attestation subject."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write attestation YAML to this file."),
) -> None:
    """Generate an accountable attestation template for owner-supplied evidence."""
    try:
        payload = yaml.safe_dump(attestation_template(kind, subject), sort_keys=False)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if output is None:
        print(payload, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")


@app.command("validate-attestation")
def validate_attestation_command(
    attestation: Path = typer.Option(..., "--attestation", help="Attestation YAML to validate."),
    expected_kind: Optional[str] = typer.Option(None, "--expected-kind", help="Optional expected kind."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write validation JSON to this file."),
) -> None:
    """Validate whether an owner/profile/impact attestation has accountable non-placeholder fields."""
    try:
        data = validate_attestation(attestation, expected_kind=expected_kind)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _write_json(data, output)


@app.command("real-world-evidence-contract")
def real_world_evidence_contract_command(
    output: Optional[Path] = typer.Option(None, "--output", help="Write evidence contract YAML to this file."),
) -> None:
    """Emit the non-generated evidence contract required for calibration and measured impact claims."""
    payload = yaml.safe_dump(real_world_evidence_contract(), sort_keys=False)
    if output is None:
        print(payload, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")


@app.command("operating-model-template")
def operating_model_template_command(
    output: Optional[Path] = typer.Option(None, "--output", help="Write operating model YAML to this file."),
) -> None:
    """Emit the human operating model needed to close review, outcome, and impact loops."""
    payload = yaml.safe_dump(operating_model_template(), sort_keys=False)
    if output is None:
        print(payload, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")


@app.command("timestamp-attestation-template")
def timestamp_attestation_template_command(
    output: Optional[Path] = typer.Option(None, "--output", help="Write timestamp attestation YAML to this file."),
) -> None:
    """Emit a template for external timestamp or evidence-repository references."""
    payload = yaml.safe_dump(timestamp_attestation_template(), sort_keys=False)
    if output is None:
        print(payload, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")


@app.command("create-case")
def create_case_command(
    case_id: str = typer.Option(..., "--case-id", help="Case identifier."),
    bundle: Path = typer.Option(..., "--bundle", help="Evidence bundle directory."),
    storage_profile: Path = typer.Option(..., "--storage-profile", help="Storage profile used for the assessment."),
    output: Path = typer.Option(..., "--output", help="Case YAML file to create."),
    policy_pack: Optional[Path] = typer.Option(None, "--policy-pack", help="Optional policy pack used for the assessment."),
    config: Optional[Path] = typer.Option(None, "--config", help="Optional threshold config used for the assessment."),
    calibration: Optional[Path] = typer.Option(None, "--calibration", help="Optional calibration report used for the assessment."),
    data_path: Optional[list[str]] = typer.Option(None, "--data-path", help="Additional data mount path."),
    app_name: Optional[str] = typer.Option(None, "--app-name", help="Optional application or workload name for evidence records."),
    workload_family: Optional[str] = typer.Option(None, "--workload-family", help="Optional workload family label."),
    path_purpose: Optional[Path] = typer.Option(None, "--path-purpose", help="Optional YAML declaring path ownership and purpose."),
    data_origin: str = typer.Option("real_workload", "--data-origin", help="Data origin label, for example real_workload or synthetic."),
    profile_origin: str = typer.Option("user_supplied", "--profile-origin", help="Storage profile origin label."),
) -> None:
    """Create a corpus case from an evidence bundle and engine decision."""
    if path_purpose is None:
        path_purpose = bundle_paths(bundle).get("path_purpose")
    try:
        app_metadata = build_app_metadata(
            app_name=app_name,
            workload_family=workload_family,
            path_purpose_file=path_purpose,
        )
        if not (app_name or workload_family or app_metadata.get("declared_data_paths")):
            app_metadata = None
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    case = create_case_from_bundle(
        case_id=case_id,
        bundle_dir=bundle,
        storage_profile_path=storage_profile,
        output_path=output,
        policy_pack_path=policy_pack,
        config_path=config,
        data_paths=data_path or [],
        calibration_path=calibration,
        app_metadata=app_metadata,
        data_origin=data_origin,
        profile_origin=profile_origin,
    )
    print(json.dumps({"created": str(output), "case_id": case["id"], "lifecycle_state": case["lifecycle_state"]}, indent=2))


@app.command("validate-case")
def validate_case_command(
    case: Path = typer.Option(..., "--case", help="Corpus case YAML file."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write validation JSON to this file."),
) -> None:
    """Validate a corpus case and report calibration readiness."""
    data = validate_case(case)
    payload = json.dumps(data, indent=2) + "\n"
    if output is None:
        print(payload, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")


@app.command("add-review")
def add_review_command(
    case: Path = typer.Option(..., "--case", help="Corpus case YAML file to update."),
    review: Path = typer.Option(..., "--review", help="Review YAML file to append."),
) -> None:
    """Append an expert review record to a case."""
    updated = add_review(case, review)
    print(json.dumps({"case_id": updated.get("id"), "lifecycle_state": updated.get("lifecycle_state"), "expert_review_count": len(updated.get("expert_reviews", []))}, indent=2))


@app.command("adjudicate-case")
def adjudicate_case_command(
    case: Path = typer.Option(..., "--case", help="Corpus case YAML file to update."),
    adjudication: Optional[Path] = typer.Option(None, "--adjudication", help="Optional adjudication YAML. If omitted, expert consensus is used."),
) -> None:
    """Record adjudication for a case, or promote expert consensus."""
    updated = adjudicate_case(case, adjudication)
    print(json.dumps({"case_id": updated.get("id"), "lifecycle_state": updated.get("lifecycle_state"), "adjudicated_fit_status": updated.get("adjudicated_fit_status")}, indent=2))


@app.command("add-outcome")
def add_outcome_command(
    case: Path = typer.Option(..., "--case", help="Corpus case YAML file to update."),
    outcome: Optional[Path] = typer.Option(None, "--outcome", help="Outcome YAML file to append."),
    status: Optional[str] = typer.Option(None, "--status", help="Outcome status when --outcome is not supplied."),
    notes: Optional[str] = typer.Option(None, "--notes", help="Outcome notes when --outcome is not supplied."),
) -> None:
    """Append an outcome record to a case."""
    updated = add_outcome(case, outcome, status=status, notes=notes)
    print(json.dumps({"case_id": updated.get("id"), "lifecycle_state": updated.get("lifecycle_state"), "outcome_count": len(updated.get("outcomes", []))}, indent=2))


@app.command("add-impact")
def add_impact_command(
    case: Path = typer.Option(..., "--case", help="Corpus case YAML file to update."),
    impact: Optional[Path] = typer.Option(None, "--impact", help="Business impact YAML file to append."),
    assessment_minutes: Optional[int] = typer.Option(None, "--assessment-minutes", help="Assessment time in minutes."),
    expert_review_minutes: Optional[int] = typer.Option(None, "--expert-review-minutes", help="Expert review time in minutes."),
    blocker_found_before_pilot: Optional[str] = typer.Option(None, "--blocker-found-before-pilot", help="true/false: whether a storage blocker was found before pilot."),
    failed_pilot_avoided: Optional[str] = typer.Option(None, "--failed-pilot-avoided", help="true/false: whether a likely failed pilot was avoided."),
    platform_gap_identified: Optional[str] = typer.Option(None, "--platform-gap-identified", help="true/false: whether a platform storage capability gap was identified."),
    decision: Optional[str] = typer.Option(None, "--decision", help="Business decision made from the assessment."),
) -> None:
    """Append a business impact record to a case."""
    updated = add_impact(
        case,
        impact,
        assessment_minutes=assessment_minutes,
        expert_review_minutes=expert_review_minutes,
        blocker_found_before_pilot=_parse_bool_text(blocker_found_before_pilot),
        failed_pilot_avoided=_parse_bool_text(failed_pilot_avoided),
        platform_gap_identified=_parse_bool_text(platform_gap_identified),
        decision=decision,
    )
    print(json.dumps({"case_id": updated.get("id"), "business_impact_count": len(updated.get("business_impact", []))}, indent=2))


@app.command("corpus-summary")
def corpus_summary_command(
    corpus_dir: Path = typer.Option(..., "--corpus-dir", help="Directory containing corpus case YAML files."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write summary JSON to this file."),
) -> None:
    """Summarize case lifecycle, outcome backlog, and readiness."""
    data = corpus_summary(corpus_dir)
    payload = json.dumps(data, indent=2) + "\n"
    if output is None:
        print(payload, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")


@app.command("outcome-backlog")
def outcome_backlog_command(
    corpus_dir: Path = typer.Option(..., "--corpus-dir", help="Directory containing corpus case YAML files."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write backlog JSON to this file."),
) -> None:
    """List trusted-label cases still waiting for decisive outcomes."""
    _write_json(outcome_backlog(corpus_dir), output)


@app.command("export-outcome-requests")
def export_outcome_requests_command(
    corpus_dir: Path = typer.Option(..., "--corpus-dir", help="Directory containing corpus case YAML files."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write outcome-request JSON to this file."),
) -> None:
    """Export the outcome fields needed to close the calibration backlog."""
    _write_json(export_outcome_requests(corpus_dir), output)


@app.command("corpus-coverage")
def corpus_coverage_command(
    corpus_dir: Path = typer.Option(..., "--corpus-dir", help="Directory containing corpus case YAML files."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write coverage JSON to this file."),
) -> None:
    """Report dataset coverage gaps by family, reason code, outcome, and capability."""
    _write_json(corpus_coverage(corpus_dir), output)


@app.command("coverage-plan")
def coverage_plan_command(
    corpus_dir: Path = typer.Option(..., "--corpus-dir", help="Directory containing corpus case YAML files."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write coverage plan JSON to this file."),
) -> None:
    """Generate calibration-grade case requests from corpus coverage gaps."""
    _write_json(coverage_plan(corpus_dir), output)


@app.command("compare-evaluations")
def compare_evaluations_command(
    old: Path = typer.Option(..., "--old", help="Previous corpus evaluation JSON."),
    new: Path = typer.Option(..., "--new", help="New corpus evaluation JSON."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write comparison JSON to this file."),
) -> None:
    """Compare two corpus evaluations and flag release-gate regressions."""
    _write_json(compare_evaluations(old, new), output)


@app.command("business-impact-summary")
def business_impact_summary_command(
    corpus_dir: Path = typer.Option(..., "--corpus-dir", help="Directory containing corpus case YAML files."),
    baseline: Optional[Path] = typer.Option(None, "--baseline", help="Optional operational baseline YAML."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write business-impact summary JSON to this file."),
) -> None:
    """Summarize measured operational impact without estimating cost."""
    try:
        data = business_impact_summary(corpus_dir, baseline)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _write_json(data, output)


@app.command("followup-sla")
def followup_sla_command(
    corpus_dir: Path = typer.Option(..., "--corpus-dir", help="Directory containing corpus case YAML files."),
    review_due_days: int = typer.Option(7, "--review-due-days", help="Days allowed for review/adjudication follow-up."),
    outcome_due_days: int = typer.Option(30, "--outcome-due-days", help="Days allowed for outcome/impact follow-up."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write follow-up SLA JSON to this file."),
) -> None:
    """Generate follow-up work items for review, outcome, and business-impact gaps."""
    _write_json(
        followup_sla(corpus_dir, review_due_days=review_due_days, outcome_due_days=outcome_due_days),
        output,
    )


@app.command("calibration-actions")
def calibration_actions_command(
    corpus_evaluation: Path = typer.Option(..., "--corpus-evaluation", help="Corpus evaluation JSON."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write calibration action JSON to this file."),
) -> None:
    """Recommend data and rule-review actions from corpus readiness blockers."""
    _write_json(calibration_actions(corpus_evaluation), output)


@app.command("trend-report")
def trend_report_command(
    decision: list[Path] = typer.Option(..., "--decision", help="Fit JSON decision in chronological order. Repeat for multiple decisions."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write trend report JSON to this file."),
) -> None:
    """Summarize multi-run decision trends for one workload."""
    _write_json(trend_report(decision), output)


@app.command("proprietary-scan")
def proprietary_scan_command(
    path: list[Path] = typer.Option(..., "--path", help="File or directory to scan. Repeat for multiple roots."),
    banned_terms: Optional[Path] = typer.Option(None, "--banned-terms", help="Text file containing user-supplied banned terms."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write scan JSON to this file."),
) -> None:
    """Scan artifacts for user-supplied proprietary terms. No default term list is bundled."""
    _write_json(proprietary_scan(path, banned_terms), output)


@app.command("handoff-bundle")
def handoff_bundle_command(
    audit_dir: Path = typer.Option(..., "--audit-dir", help="Audit output directory to package."),
    output: Path = typer.Option(..., "--output", help="ZIP file to create."),
) -> None:
    """Create a local ZIP handoff bundle with an embedded checksum manifest."""
    _write_json(handoff_bundle(audit_dir, output), None)


@app.command("run-audit")
def run_audit_command(
    output_dir: Path = typer.Option(..., "--output-dir", help="Audit output directory."),
    storage_profile: Path = typer.Option(..., "--storage-profile", help="Storage profile YAML."),
    bundle: Optional[Path] = typer.Option(None, "--bundle", help="Existing evidence bundle directory."),
    collect_current: bool = typer.Option(False, "--collect-current", help="Explicitly collect a new local bundle."),
    redact_first: bool = typer.Option(True, "--redact-first/--no-redact-first", help="Redact collected bundle evidence before writing."),
    process_redaction_mode: str = typer.Option("balanced", "--process-redaction-mode", help="Process redaction mode when collecting."),
    path_purpose: Optional[Path] = typer.Option(None, "--path-purpose", help="Optional path-purpose YAML."),
    app_name: Optional[str] = typer.Option(None, "--app-name", help="Optional application or workload name."),
    workload_family: Optional[str] = typer.Option(None, "--workload-family", help="Optional workload family label."),
    case_id: str = typer.Option("audit-case", "--case-id", help="Case id to create in the audit directory."),
    gate_mode: str = typer.Option("business_review", "--gate-mode", help="Quality gate mode."),
) -> None:
    """Run the local-only audit workflow and write all validation artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    audit_bundle = bundle
    if collect_current:
        audit_bundle = output_dir / "bundle"
        collect_local_bundle(
            audit_bundle,
            include_optional=True,
            timeout_seconds=20,
            redact_first=redact_first,
            process_redaction_mode=process_redaction_mode,
        )
    if audit_bundle is None:
        raise typer.BadParameter("--bundle is required unless --collect-current is used")

    _write_json(validate_bundle(audit_bundle), output_dir / "bundle-validation.json")
    _write_json(storage_profile_snapshot(storage_profile), output_dir / "profile-snapshot.json")
    if path_purpose is None:
        template = path_purpose_template(audit_bundle)
        (output_dir / "path-purpose-template.yml").write_text(
            yaml.safe_dump(template, sort_keys=False),
            encoding="utf-8",
        )

    paths = bundle_paths(audit_bundle)
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
    app_metadata = build_app_metadata(
        app_name=app_name,
        workload_family=workload_family,
        path_purpose_file=path_purpose,
    )
    if not (app_name or workload_family or app_metadata.get("declared_data_paths")):
        app_metadata = None
    analysis = analyze_paths(
        df=paths["df"],
        mount=paths["mount"],
        fstab=paths["fstab"],
        iostat=paths["iostat"],
        ps=paths["ps"],
        storage_profile_path=storage_profile,
        extra_evidence=extra_evidence,
        app_metadata=app_metadata,
    )
    analysis.result.warnings.extend(warning for warning in extra_warnings if warning not in analysis.result.warnings)
    write_fit_result(analysis.result, output_dir / "fit.json")
    write_mount_report(analysis.candidate_mounts, output_dir / "mounts.csv")
    _write_json(validate_decision(output_dir / "fit.json"), output_dir / "decision-validation.json")
    _write_json(
        validate_input_realism(bundle_dir=audit_bundle, storage_profile=storage_profile, path_purpose=path_purpose),
        output_dir / "input-realism.json",
    )
    create_case_from_bundle(
        case_id=case_id,
        bundle_dir=audit_bundle,
        storage_profile_path=storage_profile,
        output_path=output_dir / "corpus" / f"{case_id}.yml",
        app_metadata=app_metadata,
        data_origin="real_workload",
        profile_origin="user_supplied",
    )
    _write_json(validate_case(output_dir / "corpus" / f"{case_id}.yml"), output_dir / "case-validation.json")
    _write_json(
        quality_gate(
            input_realism=output_dir / "input-realism.json",
            decision_validation=output_dir / "decision-validation.json",
            case_validation=output_dir / "case-validation.json",
            mode=gate_mode,
        ),
        output_dir / "quality-gate.json",
    )
    _write_json(audit_manifest(output_dir), output_dir / "audit-manifest.json")
    print(json.dumps({"audit_dir": str(output_dir), "case_id": case_id}, indent=2))


@app.command("generate-full-coverage-lab")
def generate_full_coverage_lab_command(
    output_dir: Path = typer.Option(..., "--output-dir", help="Directory for generated full-coverage lab artifacts."),
    quick: bool = typer.Option(False, "--quick", help="Generate one case per family for CLI smoke tests."),
) -> None:
    """Generate deterministic full-coverage fixtures with simulated reviews, outcomes, and impact."""
    family_targets = None
    if quick:
        family_targets = {
            "relational_database": 1,
            "shared_filesystem": 1,
            "file_server": 1,
            "search_logging": 1,
            "queue_streaming": 1,
            "generic_stateful_app": 1,
        }
    _write_json(generate_full_coverage_lab(output_dir, family_targets=family_targets), output_dir / "full-coverage-lab-summary.json")
    print(json.dumps({"output_dir": str(output_dir)}, indent=2))


@app.command("generate-gap-closure-lab")
def generate_gap_closure_lab_command(
    output_dir: Path = typer.Option(..., "--output-dir", help="Directory for generated gap-closure artifacts."),
) -> None:
    """Generate deterministic edge cases and governance artifacts that close the current audit gap list."""
    _write_json(generate_gap_closure_lab(output_dir), output_dir / "gap-closure-summary.json")
    print(json.dumps({"output_dir": str(output_dir)}, indent=2))


@app.command("portfolio")
def portfolio_command(
    inventory: Path = typer.Option(..., "--inventory", help="Portfolio inventory YAML."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write portfolio JSON to this file."),
) -> None:
    """Analyze many VM evidence bundles from an offline inventory YAML."""
    data = analyze_portfolio(inventory)
    payload = json.dumps(data, indent=2) + "\n"
    if output is None:
        print(payload, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")


@app.command("evaluate-corpus")
def evaluate_corpus_command(
    corpus_dir: Path = typer.Option(..., "--corpus-dir", help="Directory containing labeled corpus case YAML files."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write evaluation JSON to this file."),
    min_outcome_cases: int = typer.Option(20, "--min-outcome-cases", help="Minimum outcome-linked cases for calibrated readiness."),
    min_outcome_coverage: float = typer.Option(0.30, "--min-outcome-coverage", help="Minimum outcome-linked corpus coverage."),
    max_pass_storage_failure_rate: float = typer.Option(0.10, "--max-pass-storage-failure-rate", help="Maximum acceptable PASS storage-failure outcome rate."),
) -> None:
    """Evaluate rules against an offline labeled corpus."""
    data = evaluate_corpus(
        corpus_dir,
        min_outcome_cases=min_outcome_cases,
        min_outcome_coverage=min_outcome_coverage,
        max_pass_storage_failure_rate=max_pass_storage_failure_rate,
    )
    payload = json.dumps(data, indent=2) + "\n"
    if output is None:
        print(payload, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")


@app.command("case-template")
def case_template_command(
    case_id: str = typer.Option(..., "--case-id", help="Case identifier for the template."),
    output: Optional[Path] = typer.Option(None, "--output", help="Write case YAML template to this file."),
) -> None:
    """Create a corpus case template with expert review and outcome fields."""
    payload = yaml.safe_dump(case_template(case_id), sort_keys=False)
    if output is None:
        print(payload, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    app()
