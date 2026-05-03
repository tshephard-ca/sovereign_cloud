from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
import typer

from .bundle import create_case_bundle, validate_case_bundle
from .bucket_config import load_bucket_config
from .cloudtrail_normalize import normalize_event, sort_events
from .cloudtrail_parse import parse_cloudtrail
from .config import load_config
from .corpus import corpus_summary_markdown, import_bundle, summarize_corpus
from .decision import (
    build_capability_ledger,
    build_cutover_brief,
    load_business_context,
    write_capability_ledger_csv,
    write_cutover_brief_json,
    write_cutover_brief_markdown,
    write_owner_questions_yaml,
    write_remediation_queue_csv,
)
from .matrix import build_matrix, matrix_markdown
from .models import ProbePlan, ProbeResults, UsageProfile
from .policy import evaluate_policy, list_policy_files, load_policy, policy_to_yaml
from .probe_plan import build_probe_plan, plan_from_yaml, plan_to_yaml
from .probes import run_probe_plan
from .questionnaire import generate_questionnaire, load_mismatches_csv, questionnaire_to_markdown
from .real_world import (
    assess_real_world_data,
    assessment_markdown,
    generate_real_world_fixture,
    simulate_real_world_results,
)
from .report import build_summary, read_json, summary_markdown, write_json, write_mismatches_csv, write_needs_csv, write_text
from .request_hints import load_request_hints
from .s3_client import S3CompatibleClient
from .safety import validate_scratch_prefix
from .usage_profile import build_usage_profile
from .validation import schema_for, validate_artifact


app = typer.Typer(help="Local-first S3-compatible endpoint compatibility preflight.")
preflight_app = typer.Typer(help="Build a cutover-focused semantic compatibility package.")
bundle_app = typer.Typer(help="Create and validate redacted compatibility case bundles.")
corpus_app = typer.Typer(help="Import and summarize local redacted case-bundle corpora.")
questionnaire_app = typer.Typer(help="Generate app-owner and field-review question sets.")
policy_app = typer.Typer(help="List, show, and evaluate workload policy packs.")
real_world_app = typer.Typer(help="Generate and assess realistic local compatibility evidence.")
lab_app = typer.Typer(help="Compatibility aliases for deterministic local lab fixtures.")
app.add_typer(preflight_app, name="preflight")
app.add_typer(bundle_app, name="bundle")
app.add_typer(corpus_app, name="corpus")
app.add_typer(questionnaire_app, name="questionnaire")
app.add_typer(policy_app, name="policy")
app.add_typer(real_world_app, name="real-world")
app.add_typer(lab_app, name="lab")


@app.command()
def analyze(
    cloudtrail: Path = typer.Option(..., "--cloudtrail", exists=True, help="CloudTrail-style file or directory."),
    source_bucket: str = typer.Option(..., "--source-bucket"),
    output_profile: Path = typer.Option(..., "--output-profile"),
    output_plan: Path = typer.Option(..., "--output-plan"),
    output_needs: Path = typer.Option(..., "--output-needs"),
    output_capability_ledger: Optional[Path] = typer.Option(None, "--output-capability-ledger"),
    top_events: int = typer.Option(500, "--top-events"),
    max_probes: int = typer.Option(100, "--max-probes"),
    config: Optional[Path] = typer.Option(None, "--config"),
    request_hints: Optional[Path] = typer.Option(None, "--request-hints"),
    bucket_config: Optional[Path] = typer.Option(None, "--bucket-config"),
    redact: bool = typer.Option(False, "--redact"),
    strict: bool = typer.Option(False, "--strict"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    del output_format
    cfg = load_config(config)
    hints = load_request_hints(request_hints)
    bucket_ctx = load_bucket_config(bucket_config)
    max_events = min(int(cfg["max_events_to_process"]), top_events)
    raw_events, parse_warnings = parse_cloudtrail(cloudtrail, max_events=max_events)
    if strict and not raw_events:
        raise typer.BadParameter("no CloudTrail records found")

    allowed_sources = set(cfg["source_event_sources"])
    normalized = [
        event
        for event in (
            normalize_event(
                raw,
                source_bucket=source_bucket,
                allowed_event_sources=allowed_sources,
                enable_bucket_from_host=bool(cfg.get("enable_bucket_from_host")),
                redact=redact,
                hash_length=int(cfg["key_hash_length"]),
            )
            for raw in raw_events
        )
        if event is not None
    ]
    normalized = sort_events(normalized)
    if strict:
        if not normalized:
            raise typer.BadParameter("no matching source-bucket events found")
        if all(not event.event_name or not event.event_source for event in normalized):
            raise typer.BadParameter("required fields eventName or eventSource are missing from all matching events")

    profile = build_usage_profile(source_bucket, len(raw_events), normalized, request_hints=hints, bucket_config=bucket_ctx)
    profile.warnings = sorted(set(profile.warnings) | set(parse_warnings))
    plan = build_probe_plan(profile, request_hints=hints, bucket_config=bucket_ctx, max_probes=max_probes)
    if strict and not plan.probes:
        raise typer.BadParameter("probe plan would contain zero probes")

    write_json(output_profile, profile)
    write_text(output_plan, plan_to_yaml(plan))
    write_needs_csv(output_needs, profile)
    if output_capability_ledger:
        write_capability_ledger_csv(output_capability_ledger, build_capability_ledger(profile, plan))
    typer.echo(f"wrote {output_profile}")
    typer.echo(f"wrote {output_plan}")
    typer.echo(f"wrote {output_needs}")
    if output_capability_ledger:
        typer.echo(f"wrote {output_capability_ledger}")


@app.command()
def probe(
    plan: Path = typer.Option(..., "--plan", exists=True),
    endpoint_url: str = typer.Option(..., "--endpoint-url"),
    target_bucket: str = typer.Option(..., "--target-bucket"),
    region: str = typer.Option(..., "--region"),
    access_key_env: str = typer.Option(..., "--access-key-env"),
    secret_key_env: str = typer.Option(..., "--secret-key-env"),
    session_token_env: Optional[str] = typer.Option(None, "--session-token-env"),
    scratch_prefix: str = typer.Option("compat-replay/", "--scratch-prefix"),
    output_results: Path = typer.Option(..., "--output-results"),
    output_mismatches: Path = typer.Option(..., "--output-mismatches"),
    config: Optional[Path] = typer.Option(None, "--config"),
    strict: bool = typer.Option(False, "--strict"),
    read_only: bool = typer.Option(False, "--read-only"),
    allow_writes: bool = typer.Option(False, "--allow-writes"),
    allow_deletes: bool = typer.Option(False, "--allow-deletes"),
    allow_multipart: bool = typer.Option(False, "--allow-multipart"),
    allow_acl_tests: bool = typer.Option(False, "--allow-acl-tests"),
    allow_object_lock_tests: bool = typer.Option(False, "--allow-object-lock-tests"),
    cleanup: bool = typer.Option(True, "--cleanup/--no-cleanup"),
    addressing_style: str = typer.Option("path", "--addressing-style"),
    no_verify_tls: bool = typer.Option(False, "--no-verify-tls"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    del output_format
    cfg = load_config(config)
    loaded_plan = plan_from_yaml(plan.read_text(encoding="utf-8"))
    if not endpoint_url:
        raise typer.BadParameter("endpoint URL is required")
    if not target_bucket:
        raise typer.BadParameter("target bucket is required")
    access_key = os.environ.get(access_key_env)
    secret_key = os.environ.get(secret_key_env)
    session_token = os.environ.get(session_token_env) if session_token_env else None
    if not access_key or not secret_key:
        raise typer.BadParameter("target credentials are missing from the named environment variables")
    prefix_errors = validate_scratch_prefix(scratch_prefix, int(cfg["min_scratch_prefix_length"]))
    if prefix_errors:
        raise typer.BadParameter("; ".join(prefix_errors))

    client = S3CompatibleClient(
        endpoint_url=endpoint_url,
        region=region,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        verify_tls=not no_verify_tls,
        addressing_style=addressing_style,
        request_timeout_seconds=int(cfg["request_timeout_seconds"]),
        retries=int(cfg["retries"]),
    )
    results, cleanup_manifest = run_probe_plan(
        loaded_plan,
        client=client,
        endpoint_url=endpoint_url,
        target_bucket=target_bucket,
        scratch_prefix=scratch_prefix,
        allow_writes=allow_writes,
        allow_deletes=allow_deletes,
        allow_acl_tests=allow_acl_tests,
        allow_multipart=allow_multipart,
        allow_object_lock_tests=allow_object_lock_tests,
        read_only=read_only,
        cleanup=cleanup,
        strict=strict,
        min_scratch_prefix_length=int(cfg["min_scratch_prefix_length"]),
        tls_verification_disabled=no_verify_tls,
    )
    write_json(output_results, results)
    write_mismatches_csv(output_mismatches, results)
    if cleanup_manifest:
        write_json(output_results.parent / "cleanup-manifest.json", cleanup_manifest)
    typer.echo(f"wrote {output_results}")
    typer.echo(f"wrote {output_mismatches}")


@app.command()
def summarize(
    profile: Path = typer.Option(..., "--profile", exists=True),
    results: Path = typer.Option(..., "--results", exists=True),
    plan: Optional[Path] = typer.Option(None, "--plan", exists=True),
    business_context: Optional[Path] = typer.Option(None, "--business-context", exists=True),
    output_summary: Path = typer.Option(..., "--output-summary"),
    output_markdown: Path = typer.Option(..., "--output-markdown"),
    output_cutover_brief: Optional[Path] = typer.Option(None, "--output-cutover-brief"),
    output_cutover_brief_markdown: Optional[Path] = typer.Option(None, "--output-cutover-brief-markdown"),
    output_remediation_queue: Optional[Path] = typer.Option(None, "--output-remediation-queue"),
    output_capability_ledger: Optional[Path] = typer.Option(None, "--output-capability-ledger"),
    strict: bool = typer.Option(False, "--strict"),
    output_format: str = typer.Option("json", "--format"),
) -> None:
    del strict, output_format
    usage_profile = UsageProfile(**read_json(profile))
    probe_results = ProbeResults(**read_json(results))
    loaded_plan = plan_from_yaml(plan.read_text(encoding="utf-8")) if plan else None
    summary = build_summary(usage_profile, probe_results, loaded_plan)
    write_json(output_summary, summary)
    write_text(output_markdown, summary_markdown(summary))
    if loaded_plan:
        context = load_business_context(business_context)
        brief = build_cutover_brief(usage_profile, loaded_plan, probe_results, summary, business_context=context)
        if output_cutover_brief:
            write_cutover_brief_json(output_cutover_brief, brief)
        if output_cutover_brief_markdown:
            write_cutover_brief_markdown(output_cutover_brief_markdown, brief)
        if output_remediation_queue:
            write_remediation_queue_csv(output_remediation_queue, [*brief.blockers, *brief.review_items])
        if output_capability_ledger:
            write_capability_ledger_csv(output_capability_ledger, brief.capability_ledger)
    typer.echo(f"wrote {output_summary}")
    typer.echo(f"wrote {output_markdown}")
    for extra in [output_cutover_brief, output_cutover_brief_markdown, output_remediation_queue, output_capability_ledger]:
        if extra:
            typer.echo(f"wrote {extra}")


@preflight_app.command("package")
def preflight_package(
    cloudtrail: Path = typer.Option(..., "--cloudtrail", exists=True, help="CloudTrail-style file or directory."),
    source_bucket: str = typer.Option(..., "--source-bucket"),
    output_dir: Path = typer.Option(..., "--output-dir"),
    request_hints: Optional[Path] = typer.Option(None, "--request-hints", exists=True),
    bucket_config: Optional[Path] = typer.Option(None, "--bucket-config", exists=True),
    business_context: Optional[Path] = typer.Option(None, "--business-context", exists=True),
    results: Optional[Path] = typer.Option(None, "--results", exists=True),
    policy: Optional[Path] = typer.Option(None, "--policy", exists=True),
    config: Optional[Path] = typer.Option(None, "--config"),
    top_events: int = typer.Option(500, "--top-events"),
    max_probes: int = typer.Option(100, "--max-probes"),
    redact: bool = typer.Option(False, "--redact"),
    strict: bool = typer.Option(False, "--strict"),
) -> None:
    """Build the core cutover preflight package from observed evidence and optional target results."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg = load_config(config)
    hints = load_request_hints(request_hints)
    bucket_ctx = load_bucket_config(bucket_config)
    max_events = min(int(cfg["max_events_to_process"]), top_events)
    raw_events, parse_warnings = parse_cloudtrail(cloudtrail, max_events=max_events)
    if strict and not raw_events:
        raise typer.BadParameter("no CloudTrail records found")
    normalized = [
        event
        for event in (
            normalize_event(
                raw,
                source_bucket=source_bucket,
                allowed_event_sources=set(cfg["source_event_sources"]),
                enable_bucket_from_host=bool(cfg.get("enable_bucket_from_host")),
                redact=redact,
                hash_length=int(cfg["key_hash_length"]),
            )
            for raw in raw_events
        )
        if event is not None
    ]
    normalized = sort_events(normalized)
    if strict and not normalized:
        raise typer.BadParameter("no matching source-bucket events found")
    profile_model = build_usage_profile(source_bucket, len(raw_events), normalized, request_hints=hints, bucket_config=bucket_ctx)
    profile_model.warnings = sorted(set(profile_model.warnings) | set(parse_warnings))
    plan_model = build_probe_plan(profile_model, request_hints=hints, bucket_config=bucket_ctx, max_probes=max_probes)
    results_model = ProbeResults(**read_json(results)) if results else None
    summary = build_summary(profile_model, results_model, plan_model)
    context = load_business_context(business_context)
    brief = build_cutover_brief(profile_model, plan_model, results_model, summary, business_context=context)

    write_json(output_dir / "usage-profile.json", profile_model)
    write_text(output_dir / "probe-plan.yml", plan_to_yaml(plan_model))
    write_needs_csv(output_dir / "compatibility-needs.csv", profile_model)
    write_capability_ledger_csv(output_dir / "capability-ledger.csv", brief.capability_ledger)
    write_json(output_dir / "compat-summary.json", summary)
    write_text(output_dir / "compat-summary.md", summary_markdown(summary))
    write_cutover_brief_json(output_dir / "cutover-brief.json", brief)
    write_cutover_brief_markdown(output_dir / "cutover-brief.md", brief)
    write_remediation_queue_csv(output_dir / "remediation-queue.csv", [*brief.blockers, *brief.review_items])
    write_owner_questions_yaml(output_dir / "owner-questions.yml", brief.owner_questions)
    if results_model:
        write_mismatches_csv(output_dir / "mismatches.csv", results_model)
    if policy:
        write_json(output_dir / "policy-evaluation.json", evaluate_policy(load_policy(policy), profile_model, results_model))
    typer.echo(f"wrote preflight package: {output_dir}")
    typer.echo(f"cutover recommendation: {brief.cutover_recommendation}")


@app.command("validate")
def validate_cmd(
    artifact: Path = typer.Argument(..., exists=True),
    artifact_type: Optional[str] = typer.Option(None, "--type"),
    output: Optional[Path] = typer.Option(None, "--output"),
    strict: bool = typer.Option(False, "--strict"),
) -> None:
    result = validate_artifact(artifact, artifact_type)
    if output:
        write_json(output, result)
    else:
        typer.echo(result.model_dump_json(indent=2))
    if strict and result.status != "PASS":
        raise typer.Exit(code=3)


@app.command("schema")
def schema_cmd(
    artifact_type: str = typer.Argument(..., help="usage-profile, probe-plan, probe-results, compat-summary, cutover-brief, case, questionnaire, policy-pack, redaction-report"),
    output: Optional[Path] = typer.Option(None, "--output"),
) -> None:
    schema = schema_for(artifact_type)
    if output:
        write_json(output, schema)
    else:
        typer.echo(yaml.safe_dump(schema, sort_keys=False))


@app.command("compare-results")
def compare_results_cmd(
    profile: Path = typer.Option(..., "--profile", exists=True),
    results: list[Path] = typer.Option(..., "--results", exists=True),
    output_matrix: Path = typer.Option(..., "--output-matrix"),
    output_markdown: Optional[Path] = typer.Option(None, "--output-markdown"),
) -> None:
    matrix = build_matrix(profile, results)
    write_json(output_matrix, matrix)
    if output_markdown:
        write_text(output_markdown, matrix_markdown(matrix))
    typer.echo(f"wrote {output_matrix}")


@bundle_app.command("create")
def bundle_create(
    profile: Path = typer.Option(..., "--profile", exists=True),
    plan: Path = typer.Option(..., "--plan", exists=True),
    output: Path = typer.Option(..., "--output"),
    results: Optional[Path] = typer.Option(None, "--results", exists=True),
    mismatches: Optional[Path] = typer.Option(None, "--mismatches", exists=True),
    summary: Optional[Path] = typer.Option(None, "--summary", exists=True),
    markdown: Optional[Path] = typer.Option(None, "--markdown", exists=True),
    cleanup_manifest: Optional[Path] = typer.Option(None, "--cleanup-manifest", exists=True),
    workload_type: str = typer.Option("unspecified", "--workload-type"),
    shareable: bool = typer.Option(True, "--shareable/--local-only"),
    strict_redaction: bool = typer.Option(True, "--strict-redaction/--no-strict-redaction"),
) -> None:
    _, report = create_case_bundle(
        profile_path=profile,
        plan_path=plan,
        results_path=results,
        mismatches_path=mismatches,
        summary_path=summary,
        markdown_path=markdown,
        cleanup_manifest_path=cleanup_manifest,
        output_path=output,
        workload_type=workload_type,
        shareable=shareable,
    )
    if strict_redaction and report.redaction_status != "PASS":
        raise typer.BadParameter("bundle redaction report did not pass")
    typer.echo(f"wrote {output}")


@bundle_app.command("validate")
def bundle_validate(
    bundle: Path = typer.Option(..., "--bundle", exists=True),
    strict_redaction: bool = typer.Option(False, "--strict-redaction"),
    output_report: Optional[Path] = typer.Option(None, "--output-report"),
) -> None:
    ok, errors, report = validate_case_bundle(bundle, strict_redaction=strict_redaction)
    if output_report:
        write_json(output_report, report)
    if errors:
        for error in errors:
            typer.echo(error, err=True)
    typer.echo("PASS" if ok else "FAIL")
    if not ok:
        raise typer.Exit(code=3)


@corpus_app.command("import")
def corpus_import(
    bundle: Path = typer.Option(..., "--bundle", exists=True),
    corpus_dir: Path = typer.Option(..., "--corpus-dir"),
    strict_redaction: bool = typer.Option(True, "--strict-redaction/--no-strict-redaction"),
) -> None:
    output = import_bundle(bundle, corpus_dir, strict_redaction=strict_redaction)
    typer.echo(f"imported {output}")


@corpus_app.command("summarize")
def corpus_summarize(
    corpus_dir: Path = typer.Option(..., "--corpus-dir", exists=True),
    output: Path = typer.Option(..., "--output"),
    output_json: Optional[Path] = typer.Option(None, "--output-json"),
) -> None:
    summary = summarize_corpus(corpus_dir)
    write_text(output, corpus_summary_markdown(summary))
    if output_json:
        write_json(output_json, summary)
    typer.echo(f"wrote {output}")


@questionnaire_app.command("generate")
def questionnaire_generate(
    profile: Path = typer.Option(..., "--profile", exists=True),
    mismatches: Optional[Path] = typer.Option(None, "--mismatches", exists=True),
    output: Path = typer.Option(..., "--output"),
    output_markdown: Optional[Path] = typer.Option(None, "--output-markdown"),
) -> None:
    usage_profile = UsageProfile(**read_json(profile))
    mismatch_rows = load_mismatches_csv(mismatches)
    questionnaire = generate_questionnaire(usage_profile, mismatch_rows)
    write_text(output, yaml.safe_dump(questionnaire.model_dump(mode="json"), sort_keys=False))
    if output_markdown:
        write_text(output_markdown, questionnaire_to_markdown(questionnaire))
    typer.echo(f"wrote {output}")


@policy_app.command("list")
def policy_list(
    policy_dir: Optional[Path] = typer.Option(None, "--policy-dir", exists=True),
) -> None:
    for path in list_policy_files(policy_dir):
        typer.echo(path.stem)


@policy_app.command("show")
def policy_show(
    policy: Path = typer.Option(..., "--policy", exists=True),
) -> None:
    typer.echo(policy_to_yaml(load_policy(policy)))


@policy_app.command("evaluate")
def policy_evaluate(
    policy: Path = typer.Option(..., "--policy", exists=True),
    profile: Path = typer.Option(..., "--profile", exists=True),
    results: Optional[Path] = typer.Option(None, "--results", exists=True),
    output: Path = typer.Option(..., "--output"),
) -> None:
    usage_profile = UsageProfile(**read_json(profile))
    probe_results = ProbeResults(**read_json(results)) if results else None
    evaluation = evaluate_policy(load_policy(policy), usage_profile, probe_results)
    write_json(output, evaluation)
    typer.echo(f"wrote {output}")


@real_world_app.command("generate")
def real_world_generate(
    output_dir: Path = typer.Option(..., "--output-dir"),
    source_bucket: str = typer.Option("source-bucket-example", "--source-bucket"),
    event_count: int = typer.Option(180, "--event-count"),
) -> None:
    fixture = generate_real_world_fixture(output_dir, source_bucket=source_bucket, event_count=event_count)
    write_json(output_dir / "generated-fixture.json", fixture)
    typer.echo(f"wrote {output_dir}")


@real_world_app.command("simulate-results")
def real_world_simulate_results(
    plan: Path = typer.Option(..., "--plan", exists=True),
    output_results: Path = typer.Option(..., "--output-results"),
    output_mismatches: Path = typer.Option(..., "--output-mismatches"),
    scenario: str = typer.Option("semantic-gaps", "--scenario"),
) -> None:
    simulate_real_world_results(plan, output_results, output_mismatches, scenario=scenario)
    typer.echo(f"wrote {output_results}")
    typer.echo(f"wrote {output_mismatches}")


@real_world_app.command("assess")
def real_world_assess(
    cloudtrail: Optional[Path] = typer.Option(None, "--cloudtrail", exists=True),
    request_hints: Optional[Path] = typer.Option(None, "--request-hints", exists=True),
    bucket_config: Optional[Path] = typer.Option(None, "--bucket-config", exists=True),
    http_trace: Optional[Path] = typer.Option(None, "--http-trace", exists=True),
    server_access_log: Optional[Path] = typer.Option(None, "--server-access-log", exists=True),
    policy_context: Optional[Path] = typer.Option(None, "--policy-context", exists=True),
    business_context: Optional[Path] = typer.Option(None, "--business-context", exists=True),
    corpus_calibration: Optional[Path] = typer.Option(None, "--corpus-calibration", exists=True),
    profile: Optional[Path] = typer.Option(None, "--profile", exists=True),
    plan: Optional[Path] = typer.Option(None, "--plan", exists=True),
    results: Optional[Path] = typer.Option(None, "--results", exists=True),
    summary: Optional[Path] = typer.Option(None, "--summary", exists=True),
    matrix: Optional[Path] = typer.Option(None, "--matrix", exists=True),
    questionnaire: Optional[Path] = typer.Option(None, "--questionnaire", exists=True),
    output_json: Path = typer.Option(..., "--output-json"),
    output_markdown: Path = typer.Option(..., "--output-markdown"),
) -> None:
    assessment = assess_real_world_data(
        cloudtrail_path=cloudtrail,
        request_hints_path=request_hints,
        bucket_config_path=bucket_config,
        http_trace_path=http_trace,
        server_access_log_path=server_access_log,
        policy_context_path=policy_context,
        business_context_path=business_context,
        corpus_calibration_path=corpus_calibration,
        profile_path=profile,
        plan_path=plan,
        results_path=results,
        summary_path=summary,
        matrix_path=matrix,
        questionnaire_path=questionnaire,
    )
    write_json(output_json, assessment)
    write_text(output_markdown, assessment_markdown(assessment))
    typer.echo(f"wrote {output_json}")
    typer.echo(f"wrote {output_markdown}")


@lab_app.command("generate")
def lab_generate(
    output_dir: Path = typer.Option(..., "--output-dir"),
    source_bucket: str = typer.Option("source-bucket-example", "--source-bucket"),
    event_count: int = typer.Option(180, "--event-count"),
) -> None:
    """Compatibility alias for real-world generate."""
    fixture = generate_real_world_fixture(output_dir, source_bucket=source_bucket, event_count=event_count)
    write_json(output_dir / "generated-fixture.json", fixture)
    typer.echo(f"wrote lab fixture: {output_dir}")


@lab_app.command("simulate-results")
def lab_simulate_results(
    plan: Path = typer.Option(..., "--plan", exists=True),
    output_results: Path = typer.Option(..., "--output-results"),
    output_mismatches: Path = typer.Option(..., "--output-mismatches"),
    scenario: str = typer.Option("semantic-gaps", "--scenario"),
) -> None:
    """Compatibility alias for real-world simulate-results."""
    simulate_real_world_results(plan, output_results, output_mismatches, scenario=scenario)
    typer.echo(f"wrote {output_results}")
    typer.echo(f"wrote {output_mismatches}")


@lab_app.command("assess")
def lab_assess(
    cloudtrail: Optional[Path] = typer.Option(None, "--cloudtrail", exists=True),
    request_hints: Optional[Path] = typer.Option(None, "--request-hints", exists=True),
    bucket_config: Optional[Path] = typer.Option(None, "--bucket-config", exists=True),
    http_trace: Optional[Path] = typer.Option(None, "--http-trace", exists=True),
    server_access_log: Optional[Path] = typer.Option(None, "--server-access-log", exists=True),
    policy_context: Optional[Path] = typer.Option(None, "--policy-context", exists=True),
    business_context: Optional[Path] = typer.Option(None, "--business-context", exists=True),
    corpus_calibration: Optional[Path] = typer.Option(None, "--corpus-calibration", exists=True),
    profile: Optional[Path] = typer.Option(None, "--profile", exists=True),
    plan: Optional[Path] = typer.Option(None, "--plan", exists=True),
    results: Optional[Path] = typer.Option(None, "--results", exists=True),
    summary: Optional[Path] = typer.Option(None, "--summary", exists=True),
    matrix: Optional[Path] = typer.Option(None, "--matrix", exists=True),
    questionnaire: Optional[Path] = typer.Option(None, "--questionnaire", exists=True),
    output_json: Path = typer.Option(..., "--output-json"),
    output_markdown: Path = typer.Option(..., "--output-markdown"),
) -> None:
    """Compatibility alias for real-world assess."""
    assessment = assess_real_world_data(
        cloudtrail_path=cloudtrail,
        request_hints_path=request_hints,
        bucket_config_path=bucket_config,
        http_trace_path=http_trace,
        server_access_log_path=server_access_log,
        policy_context_path=policy_context,
        business_context_path=business_context,
        corpus_calibration_path=corpus_calibration,
        profile_path=profile,
        plan_path=plan,
        results_path=results,
        summary_path=summary,
        matrix_path=matrix,
        questionnaire_path=questionnaire,
    )
    write_json(output_json, assessment)
    write_text(output_markdown, assessment_markdown(assessment))
    typer.echo(f"wrote {output_json}")
    typer.echo(f"wrote {output_markdown}")


def analyze_to_plan_for_tests(cloudtrail: Path, source_bucket: str, redact: bool = False) -> tuple[UsageProfile, ProbePlan]:
    cfg = load_config(None)
    raw_events, _ = parse_cloudtrail(cloudtrail)
    normalized = [
        event
        for event in (
            normalize_event(raw, source_bucket=source_bucket, allowed_event_sources=set(cfg["source_event_sources"]), redact=redact)
            for raw in raw_events
        )
        if event is not None
    ]
    profile = build_usage_profile(source_bucket, len(raw_events), sort_events(normalized))
    return profile, build_probe_plan(profile)


if __name__ == "__main__":  # pragma: no cover
    app()
