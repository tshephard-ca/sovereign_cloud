"""Typer CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

import typer
import yaml

from .backup_inventory import parse_backup_inventory
from .assessment import build_preflight_assessment
from .config import load_config
from .dns_log import parse_dns_log
from .generate_data import SAMPLE_SCENARIOS, generate_benchmark_data, generate_role_tag_worksheet, generate_sample_data, init_inputs
from .human_reports import (
    bundle_evidence,
    load_findings_csv,
    load_observed_csv,
    load_summary_json,
    write_checklist,
    write_markdown_report,
    write_questions,
)
from .known_prereqs import load_known_prereqs
from .pipeline import analyze_inputs
from .preflight_package import PreflightPackage, load_preflight_package
from .redact import redact_outputs
from .report import write_findings_csv, write_observed_csv, write_owner_worklist_csv, write_preflight_assessment_json, write_summary_json
from .resolver_hints import load_resolver_hints
from .schemas import schema_catalog
from .support_files import load_owner_map, recovery_set_names_from_metadata
from .validation import build_validation_report
from .window_compare import compare_windows


app = typer.Typer(help="Local-only recovery-set prerequisite linter.")


@app.command("analyze")
def analyze_command(
    backup_inventory: Path = typer.Option(..., "--backup-inventory", help="Backup inventory CSV."),
    dns_log: Path = typer.Option(..., "--dns-log", help="Normalized DNS query log CSV."),
    recovery_set: str | None = typer.Option(None, "--recovery-set", help="Recovery set name to evaluate."),
    output_findings: Path = typer.Option(..., "--output-findings", "--output-coverage-gaps", help="Output coverage-gaps/findings CSV path."),
    output_observed: Path = typer.Option(..., "--output-observed", "--output-evidence-detail", help="Output evidence-detail/observed-prerequisites CSV path."),
    summary: Path = typer.Option(..., "--summary", help="Output summary JSON path."),
    known_prereqs: Path | None = typer.Option(None, "--known-prereqs", "--prerequisite-catalog", help="Optional prerequisite catalog rules YAML."),
    resolver_hints: Path | None = typer.Option(None, "--resolver-hints", "--required-resolvers", help="Optional required resolver hints YAML."),
    answer_map: Path | None = typer.Option(None, "--answer-map", help="Optional offline DNS answer map CSV."),
    accepted_risks: Path | None = typer.Option(None, "--accepted-risks", help="Optional accepted-risk YAML."),
    recovery_sets: Path | None = typer.Option(None, "--recovery-sets", help="Optional recovery-set metadata YAML."),
    owner_map: Path | None = typer.Option(None, "--owner-map", help="Optional owner-map CSV for assessment routing."),
    config: Path | None = typer.Option(None, "--config", "--policy", help="Optional policy/threshold config YAML."),
    policy_pack: str | None = typer.Option(None, "--policy-pack", help="Bundled policy pack name."),
    window_hours: int | None = typer.Option(None, "--window-hours", help="DNS time window in hours."),
    compare_window_hours: list[int] = typer.Option([], "--compare-window-hours", help="Additional DNS windows to compare in summary JSON."),
    output_assessment: Path | None = typer.Option(None, "--output-assessment", help="Optional business-facing preflight assessment JSON."),
    output_owner_worklist: Path | None = typer.Option(None, "--output-owner-worklist", help="Optional owner-routed worklist CSV."),
    strict: bool = typer.Option(False, "--strict", help="Fail on missing required input structure."),
    redact: bool = typer.Option(False, "--redact", help="Redact output hostnames and IP addresses."),
    include_unmapped_clients: bool = typer.Option(False, "--include-unmapped-clients", help="Include unmapped DNS clients as low-confidence evidence."),
    include_external: bool = typer.Option(False, "--include-external", help="Include external query names as low-confidence evidence."),
    min_query_count: int | None = typer.Option(None, "--min-query-count", help="Minimum repeated query count before heuristic confidence improves."),
    output_format: str = typer.Option("csv", "--format", help="Output format. The MVP supports csv."),
) -> None:
    if output_format.lower() != "csv":
        raise typer.BadParameter("only csv output is supported in the MVP", param_hint="--format")
    try:
        result = analyze_inputs(
            backup_inventory=backup_inventory,
            dns_log=dns_log,
            recovery_set_name=recovery_set,
            known_prereqs_path=known_prereqs,
            resolver_hints_path=resolver_hints,
            answer_map_path=answer_map,
            accepted_risks_path=accepted_risks,
            recovery_sets_path=recovery_sets,
            config_path=config,
            policy_pack=policy_pack,
            window_hours=window_hours,
            strict=strict,
            include_unmapped_clients=include_unmapped_clients,
            include_external=include_external,
            min_query_count=min_query_count,
        )
        findings = result.findings
        observed = result.observed
        output_summary = result.summary
        if compare_window_hours:
            output_summary.window_comparison = compare_windows(
                backup_inventory=backup_inventory,
                dns_log=dns_log,
                recovery_set_name=recovery_set,
                windows=compare_window_hours,
                known_prereqs_path=known_prereqs,
                resolver_hints_path=resolver_hints,
                answer_map_path=answer_map,
                accepted_risks_path=accepted_risks,
                recovery_sets_path=recovery_sets,
                config_path=config,
                policy_pack=policy_pack,
                include_unmapped_clients=include_unmapped_clients,
                include_external=include_external,
                min_query_count=min_query_count,
            )
        if redact:
            findings, observed, output_summary = redact_outputs(findings, observed, output_summary)
        cfg = load_config(config, policy_pack=policy_pack)
        write_findings_csv(
            output_findings,
            findings,
            max_examples=int(cfg.get("max_examples_per_finding", 5)),
            max_source_rows=int(cfg.get("max_source_rows_per_finding", 20)),
        )
        write_observed_csv(output_observed, observed)
        write_summary_json(summary, output_summary)
        if output_assessment or output_owner_worklist:
            assessment = build_preflight_assessment(findings=findings, summary=output_summary, owner_map=load_owner_map(owner_map))
            if output_assessment:
                write_preflight_assessment_json(output_assessment, assessment)
            if output_owner_worklist:
                write_owner_worklist_csv(output_owner_worklist, assessment.owner_work_items)
        for warning in result.summary.warnings:
            typer.echo(f"warning: {warning}", err=True)
        typer.echo(f"lint status: {output_summary.lint_status}")
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("analyze-package")
def analyze_package_command(
    package: Path = typer.Option(..., "--package", help="Preflight input package manifest YAML."),
    output_dir: Path = typer.Option(..., "--output-dir", help="Directory for the complete preflight output bundle."),
    compare_window_hours: list[int] = typer.Option([], "--compare-window-hours", help="Additional DNS windows to compare. Overrides manifest when supplied."),
    strict: bool = typer.Option(False, "--strict", help="Fail on missing required input structure."),
    redact: bool = typer.Option(False, "--redact", help="Redact output hostnames and IP addresses."),
) -> None:
    try:
        preflight_package = load_preflight_package(package)
        paths = _package_output_paths(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        result = _analyze_loaded_package(preflight_package, strict=strict)
        windows = compare_window_hours or preflight_package.compare_window_hours
        if windows:
            result.summary.window_comparison = compare_windows(
                backup_inventory=_required_input(preflight_package, "backup_inventory"),
                dns_log=_required_input(preflight_package, "dns_log"),
                recovery_set_name=preflight_package.recovery_set,
                windows=windows,
                known_prereqs_path=preflight_package.input_path("known_prereqs"),
                resolver_hints_path=preflight_package.input_path("resolver_hints"),
                answer_map_path=preflight_package.input_path("answer_map"),
                accepted_risks_path=preflight_package.input_path("accepted_risks"),
                recovery_sets_path=preflight_package.input_path("recovery_sets"),
                config_path=preflight_package.input_path("config"),
                policy_pack=preflight_package.policy_pack or None,
                include_unmapped_clients=preflight_package.include_unmapped_clients,
                include_external=preflight_package.include_external,
                min_query_count=preflight_package.min_query_count,
            )
        findings = result.findings
        observed = result.observed
        summary = result.summary
        if redact:
            findings, observed, summary = redact_outputs(findings, observed, summary)
        owner_entries = load_owner_map(preflight_package.input_path("owner_map"))
        assessment = build_preflight_assessment(findings=findings, summary=summary, owner_map=owner_entries)
        cfg = _load_optional_yaml(preflight_package.input_path("config"))
        write_findings_csv(paths["coverage_gaps"], findings)
        write_observed_csv(paths["evidence_detail"], observed)
        write_summary_json(paths["summary"], summary)
        write_preflight_assessment_json(paths["assessment"], assessment)
        write_owner_worklist_csv(paths["owner_worklist"], assessment.owner_work_items)
        write_markdown_report(paths["report"], findings, summary, owner_map=owner_entries)
        write_questions(paths["questions"], findings, owner_map=owner_entries)
        write_checklist(paths["checklist"], observed, owner_map=owner_entries)
        bundle_evidence(
            findings=findings,
            observed=observed,
            summary=summary,
            output=paths["bundle"],
            redact=False,
            config=cfg,
            input_paths=_package_input_paths(preflight_package) + [package],
            assessment=assessment,
            owner_work_items=assessment.owner_work_items,
        )
        for warning in summary.warnings:
            typer.echo(f"warning: {warning}", err=True)
        typer.echo(f"preflight decision: {assessment.decision}")
        typer.echo(f"wrote preflight assessment to {paths['assessment']}")
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("validate-inputs")
def validate_inputs_command(
    backup_inventory: Path = typer.Option(..., "--backup-inventory", help="Backup inventory CSV."),
    dns_log: Path = typer.Option(..., "--dns-log", help="Normalized DNS query log CSV."),
    known_prereqs: Path | None = typer.Option(None, "--known-prereqs", "--prerequisite-catalog", help="Optional prerequisite catalog rules YAML."),
    resolver_hints: Path | None = typer.Option(None, "--resolver-hints", "--required-resolvers", help="Optional required resolver hints YAML."),
    config: Path | None = typer.Option(None, "--config", "--policy", help="Optional policy/threshold config YAML."),
    policy_pack: str | None = typer.Option(None, "--policy-pack", help="Bundled policy pack name."),
    explain: bool = typer.Option(False, "--explain", help="Print a JSON validation explain report."),
    validation_report: Path | None = typer.Option(None, "--validation-report", help="Write validation explain report JSON."),
    strict: bool = typer.Option(False, "--strict", help="Fail on missing required input structure."),
) -> None:
    try:
        if explain or validation_report:
            report = build_validation_report(
                backup_inventory=backup_inventory,
                dns_log=dns_log,
                known_prereqs=known_prereqs,
                resolver_hints=resolver_hints,
                config=config,
                strict=strict,
            )
            text = json.dumps(report, indent=2)
            if validation_report:
                validation_report.parent.mkdir(parents=True, exist_ok=True)
                validation_report.write_text(text + "\n", encoding="utf-8")
            if explain:
                typer.echo(text)
            for warning in report["backup_inventory"]["warnings"] + report["dns_log"]["warnings"]:
                typer.echo(f"warning: {warning}", err=True)
            typer.echo("inputs valid")
            return
        backup = parse_backup_inventory(backup_inventory, strict=strict)
        dns = parse_dns_log(dns_log, strict=strict)
        load_known_prereqs(known_prereqs)
        load_resolver_hints(resolver_hints, strict=strict)
        load_config(config, policy_pack=policy_pack)
        for warning in backup.warnings + dns.warnings:
            typer.echo(f"warning: {warning}", err=True)
        typer.echo("inputs valid")
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("schema")
def schema_command(
    name: str = typer.Option("all", "--name", help="Schema name or all."),
    output: Path | None = typer.Option(None, "--output", help="Optional output JSON path."),
) -> None:
    catalog = schema_catalog()
    payload: object = catalog if name == "all" else _schema_lookup(catalog, name)
    text = json.dumps(payload, indent=2, sort_keys=True)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    else:
        typer.echo(text)


@app.command("init-inputs")
def init_inputs_command(
    output_dir: Path = typer.Option(..., "--output-dir", help="Directory for blank input templates."),
) -> None:
    try:
        init_inputs(output_dir)
        typer.echo(f"created input templates in {output_dir}")
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("generate-sample-data")
def generate_sample_data_command(
    scenario: str = typer.Option("missing-core-services", "--scenario", help="Sample scenario name."),
    output_dir: Path = typer.Option(..., "--output-dir", help="Output directory for generated inputs and expected outputs."),
) -> None:
    try:
        actual_scenario = "missing-directory-service" if scenario == "missing-core-services" else scenario
        generate_sample_data(actual_scenario, output_dir)
        typer.echo(f"generated sample scenario {actual_scenario} in {output_dir}")
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        typer.echo(f"valid scenarios: {', '.join(SAMPLE_SCENARIOS)}", err=True)
        raise typer.Exit(1) from exc


@app.command("generate-benchmark-data")
def generate_benchmark_data_command(
    output_dir: Path = typer.Option(..., "--output-dir", help="Output directory for benchmark inputs."),
    protected_systems: int = typer.Option(500, "--protected-systems", min=10, help="Approximate protected-system count."),
    queries: int = typer.Option(100000, "--queries", min=1, help="Number of DNS query rows to generate."),
    missing_prereq_rate: float = typer.Option(0.15, "--missing-prereq-rate", min=0.0, max=1.0, help="Probability shared prerequisites are excluded."),
    seed: int = typer.Option(7, "--seed", help="Deterministic random seed."),
    timestamp_span_hours: int = typer.Option(24, "--timestamp-span-hours", min=1, help="Timestamp span for the main DNS query CSV."),
    outcome_profile: str = typer.Option("fail", "--outcome-profile", help="Benchmark outcome profile: pass, review, fail, or mixed."),
) -> None:
    try:
        generate_benchmark_data(
            output_dir,
            protected_systems=protected_systems,
            queries=queries,
            missing_prereq_rate=missing_prereq_rate,
            seed=seed,
            timestamp_span_hours=timestamp_span_hours,
            outcome_profile=outcome_profile,
        )
        typer.echo(f"generated benchmark inputs in {output_dir}")
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("generate-role-tag-worksheet")
def role_tag_worksheet_command(
    backup_inventory: Path = typer.Option(..., "--backup-inventory", help="Backup inventory CSV."),
    output: Path = typer.Option(..., "--output", help="Output worksheet CSV."),
) -> None:
    try:
        generate_role_tag_worksheet(backup_inventory, output)
        typer.echo(f"wrote role-tag worksheet to {output}")
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("compare-recovery-sets")
def compare_recovery_sets_command(
    backup_inventory: Path = typer.Option(..., "--backup-inventory", help="Backup inventory CSV."),
    dns_log: Path = typer.Option(..., "--dns-log", help="Normalized DNS query log CSV."),
    output: Path = typer.Option(..., "--output", help="Output comparison JSON."),
    recovery_set: list[str] = typer.Option([], "--recovery-set", help="Recovery set name to compare. May be repeated."),
    recovery_sets: Path | None = typer.Option(None, "--recovery-sets", help="Optional recovery-set metadata YAML. Used when --recovery-set is omitted."),
    known_prereqs: Path | None = typer.Option(None, "--known-prereqs", "--prerequisite-catalog", help="Optional prerequisite catalog rules YAML."),
    resolver_hints: Path | None = typer.Option(None, "--resolver-hints", "--required-resolvers", help="Optional required resolver hints YAML."),
    answer_map: Path | None = typer.Option(None, "--answer-map", help="Optional offline DNS answer map CSV."),
    accepted_risks: Path | None = typer.Option(None, "--accepted-risks", help="Optional accepted-risk YAML."),
    config: Path | None = typer.Option(None, "--config", "--policy", help="Optional policy/threshold config YAML."),
    policy_pack: str | None = typer.Option(None, "--policy-pack", help="Bundled policy pack name."),
    window_hours: int | None = typer.Option(None, "--window-hours", help="DNS time window in hours."),
    include_unmapped_clients: bool = typer.Option(False, "--include-unmapped-clients", help="Include unmapped DNS clients as low-confidence evidence."),
    include_external: bool = typer.Option(False, "--include-external", help="Include external query names as low-confidence evidence."),
) -> None:
    try:
        names = list(dict.fromkeys(recovery_set or recovery_set_names_from_metadata(recovery_sets)))
        if not names:
            raise typer.BadParameter("provide --recovery-set or --recovery-sets with at least one set")
        comparisons = []
        for name in names:
            result = analyze_inputs(
                backup_inventory=backup_inventory,
                dns_log=dns_log,
                recovery_set_name=name,
                known_prereqs_path=known_prereqs,
                resolver_hints_path=resolver_hints,
                answer_map_path=answer_map,
                accepted_risks_path=accepted_risks,
                recovery_sets_path=recovery_sets,
                config_path=config,
                policy_pack=policy_pack,
                window_hours=window_hours,
                include_unmapped_clients=include_unmapped_clients,
                include_external=include_external,
            )
            comparisons.append(
                {
                    "recovery_set": name,
                    "lint_status": result.summary.lint_status,
                    "findings": result.summary.findings,
                    "top_missing_prerequisites": result.summary.top_missing_prerequisites,
                    "recovery_set_systems": result.summary.input.get("recovery_set_systems", 0),
                    "warnings": result.summary.warnings,
                    "recovery_set_metadata": result.summary.run_metadata.get("recovery_set_metadata", {}),
                }
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"schema_version": "1.0", "recovery_sets": comparisons}, indent=2) + "\n", encoding="utf-8")
        typer.echo(f"wrote recovery-set comparison to {output}")
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("report")
def report_command(
    findings: Path = typer.Option(..., "--findings", help="Findings CSV."),
    summary: Path = typer.Option(..., "--summary", help="Summary JSON."),
    output: Path = typer.Option(..., "--output", help="Output Markdown report."),
    owner_map: Path | None = typer.Option(None, "--owner-map", help="Optional owner-map CSV."),
) -> None:
    try:
        write_markdown_report(output, load_findings_csv(findings), load_summary_json(summary), owner_map=load_owner_map(owner_map))
        typer.echo(f"wrote report to {output}")
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("generate-questions")
def questions_command(
    findings: Path = typer.Option(..., "--findings", help="Findings CSV."),
    output: Path = typer.Option(..., "--output", help="Output Markdown questions."),
    owner_map: Path | None = typer.Option(None, "--owner-map", help="Optional owner-map CSV."),
    include_info: bool = typer.Option(False, "--include-info", help="Include INFO and optional findings in handoff questions."),
) -> None:
    try:
        write_questions(output, load_findings_csv(findings), owner_map=load_owner_map(owner_map), include_info=include_info)
        typer.echo(f"wrote questions to {output}")
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("checklist")
def checklist_command(
    observed: Path = typer.Option(..., "--observed", help="Observed prerequisites CSV."),
    output: Path = typer.Option(..., "--output", help="Output checklist CSV."),
    owner_map: Path | None = typer.Option(None, "--owner-map", help="Optional owner-map CSV."),
) -> None:
    try:
        write_checklist(output, load_observed_csv(observed), owner_map=load_owner_map(owner_map))
        typer.echo(f"wrote checklist to {output}")
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("bundle-evidence")
def bundle_evidence_command(
    findings: Path = typer.Option(..., "--findings", help="Findings CSV."),
    observed: Path = typer.Option(..., "--observed", help="Observed prerequisites CSV."),
    summary: Path = typer.Option(..., "--summary", help="Summary JSON."),
    output: Path = typer.Option(..., "--output", help="Output ZIP bundle."),
    config: Path | None = typer.Option(None, "--config", "--policy", help="Optional policy/config YAML to include."),
    redact: bool = typer.Option(False, "--redact", help="Redact hostnames and IPs in bundled outputs."),
    input_file: list[Path] = typer.Option([], "--input-file", help="Input file to fingerprint in bundle metadata."),
) -> None:
    try:
        cfg = yaml.safe_load(config.read_text(encoding="utf-8")) if config else {}
        bundle_evidence(
            findings=load_findings_csv(findings),
            observed=load_observed_csv(observed),
            summary=load_summary_json(summary),
            output=output,
            redact=redact,
            config=cfg,
            input_paths=input_file,
        )
        typer.echo(f"wrote evidence bundle to {output}")
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


def _analyze_loaded_package(preflight_package: PreflightPackage, *, strict: bool) -> object:
    return analyze_inputs(
        backup_inventory=_required_input(preflight_package, "backup_inventory"),
        dns_log=_required_input(preflight_package, "dns_log"),
        recovery_set_name=preflight_package.recovery_set,
        known_prereqs_path=preflight_package.input_path("known_prereqs"),
        resolver_hints_path=preflight_package.input_path("resolver_hints"),
        answer_map_path=preflight_package.input_path("answer_map"),
        accepted_risks_path=preflight_package.input_path("accepted_risks"),
        recovery_sets_path=preflight_package.input_path("recovery_sets"),
        config_path=preflight_package.input_path("config"),
        policy_pack=preflight_package.policy_pack or None,
        window_hours=preflight_package.window_hours,
        strict=strict,
        include_unmapped_clients=preflight_package.include_unmapped_clients,
        include_external=preflight_package.include_external,
        min_query_count=preflight_package.min_query_count,
    )


def _required_input(preflight_package: PreflightPackage, name: str) -> Path:
    path = preflight_package.input_path(name)
    if path is None:
        raise ValueError(f"preflight package is missing required input {name}")
    return path


def _package_input_paths(preflight_package: PreflightPackage) -> list[Path]:
    return [path for path in preflight_package.inputs.values() if path is not None]


def _package_output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "coverage_gaps": output_dir / "coverage_gaps.csv",
        "evidence_detail": output_dir / "evidence_detail.csv",
        "summary": output_dir / "summary.json",
        "assessment": output_dir / "preflight_assessment.json",
        "owner_worklist": output_dir / "owner_worklist.csv",
        "report": output_dir / "preflight_report.md",
        "questions": output_dir / "handoff_questions.md",
        "checklist": output_dir / "recovery_prereq_checklist.csv",
        "bundle": output_dir / "preflight_evidence_bundle.zip",
    }


def _load_optional_yaml(path: Path | None) -> dict[str, object]:
    if path is None or not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(loaded, dict):
        return loaded
    return {}


def _schema_lookup(catalog: dict[str, object], name: str) -> object:
    current: object = catalog
    for part in name.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise typer.BadParameter(f"unknown schema path {name!r}")
    return current


if __name__ == "__main__":
    app()
