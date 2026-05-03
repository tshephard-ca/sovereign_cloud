"""Typer CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .access_matrix import build_access_matrix, build_boundary_coverage, write_access_matrix_csv, write_boundary_coverage_csv
from .canary_generate import generate_canary_pack, load_pack, write_pack, write_queries_csv
from .config import load_config
from .content_set import load_content_set
from .demo_data import generate_demo_fixtures as generate_demo_fixtures_impl
from .demo_runner import run_demo as run_demo_impl
from .endpoint_profile import load_endpoint_profile
from .fixture_quality import assess_fixture, write_fixture_quality_json, write_fixture_quality_markdown
from .handoff import create_handoff_bundle
from .junit import write_junit
from .models import TestUsers
from .permissions import load_permissions
from .report import load_results, write_markdown_report
from .scoring import run_pack, write_results_json, write_samples_csv
from .users import load_users
from .validators import validate_inputs


app = typer.Typer(help="Local-first permission canary regression harness.")


@app.command("validate")
def validate_command(
    content: Path = typer.Option(..., "--content"),
    users: Path = typer.Option(..., "--users"),
    permissions: Path = typer.Option(..., "--permissions"),
    endpoint: Path = typer.Option(..., "--endpoint"),
    config: Path | None = typer.Option(None, "--config"),
    strict: bool = typer.Option(False, "--strict"),
) -> None:
    try:
        report = validate_inputs(content_path=content, users_path=users, permissions_path=permissions, endpoint_path=endpoint, config_path=config, strict=strict)
        typer.echo(json.dumps(report, indent=2))
        if not report["valid"]:
            raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("assess-fixture")
def assess_fixture_command(
    content: Path = typer.Option(..., "--content"),
    users: Path = typer.Option(..., "--users"),
    permissions: Path = typer.Option(..., "--permissions"),
    endpoint: Path = typer.Option(..., "--endpoint"),
    config: Path | None = typer.Option(None, "--config"),
    pack: Path | None = typer.Option(None, "--pack"),
    output_quality_json: Path = typer.Option(..., "--output-quality-json"),
    output_quality_markdown: Path | None = typer.Option(None, "--output-quality-markdown"),
    output_access_matrix: Path | None = typer.Option(None, "--output-access-matrix"),
    output_boundary_coverage: Path | None = typer.Option(None, "--output-boundary-coverage"),
) -> None:
    try:
        loaded_content = load_content_set(content)
        loaded_users = load_users(users)
        loaded_permissions = load_permissions(permissions)
        loaded_endpoint = load_endpoint_profile(endpoint)
        loaded_config = load_config(config)
        loaded_pack = load_pack(pack) if pack else None
        report = assess_fixture(loaded_content, loaded_users, loaded_permissions, loaded_endpoint, loaded_config, loaded_pack)
        write_fixture_quality_json(output_quality_json, report)
        if output_quality_markdown:
            write_fixture_quality_markdown(output_quality_markdown, report)
        access_rows = build_access_matrix(loaded_content, loaded_users, loaded_permissions, loaded_config, loaded_pack)
        if output_access_matrix:
            write_access_matrix_csv(output_access_matrix, access_rows)
        if output_boundary_coverage:
            write_boundary_coverage_csv(output_boundary_coverage, build_boundary_coverage(access_rows))
        typer.echo(f"fixture quality: {report['quality_grade']}")
        if not report["valid"]:
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("generate")
def generate_command(
    content: Path = typer.Option(..., "--content"),
    users: Path = typer.Option(..., "--users"),
    permissions: Path = typer.Option(..., "--permissions"),
    output_pack: Path = typer.Option(..., "--output-pack"),
    output_queries: Path = typer.Option(..., "--output-queries"),
    queries_per_user: int = typer.Option(10, "--queries-per-user"),
    config: Path | None = typer.Option(None, "--config"),
    strict: bool = typer.Option(False, "--strict"),
    now: str | None = typer.Option(None, "--now"),
) -> None:
    try:
        pack = generate_canary_pack(
            content=load_content_set(content, strict=strict),
            users=load_users(users, strict=strict),
            permissions=load_permissions(permissions),
            queries_per_user=queries_per_user,
            config=load_config(config),
            now=now,
            strict=strict,
        )
        write_pack(output_pack, pack)
        write_queries_csv(output_queries, pack)
        for warning in pack.warnings:
            typer.echo(f"warning: {warning}", err=True)
        typer.echo(f"generated {len(pack.test_cases)} canary queries")
        if strict and pack.warnings:
            raise typer.Exit(2)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2 if "INSUFFICIENT_CANARY_COVERAGE" in str(exc) else 1) from exc


@app.command("run")
def run_command(
    pack: Path = typer.Option(..., "--pack"),
    endpoint: Path = typer.Option(..., "--endpoint"),
    output_results: Path = typer.Option(..., "--output-results"),
    output_samples: Path = typer.Option(..., "--output-samples", "--output-test-results"),
    content: Path | None = typer.Option(None, "--content"),
    config: Path | None = typer.Option(None, "--config"),
    strict: bool = typer.Option(False, "--strict"),
    redact: bool = typer.Option(False, "--redact"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    no_network: bool = typer.Option(False, "--no-network"),
    fail_on_review: bool = typer.Option(False, "--fail-on-review"),
    max_queries: int | None = typer.Option(None, "--max-queries"),
    request_timeout_seconds: int | None = typer.Option(None, "--request-timeout-seconds"),
    now: str | None = typer.Option(None, "--now"),
) -> None:
    try:
        loaded_pack = load_pack(pack)
        if max_queries is not None:
            loaded_pack.test_cases = loaded_pack.test_cases[:max_queries]
        results = run_pack(
            pack=loaded_pack,
            endpoint=load_endpoint_profile(endpoint, strict=strict),
            users=TestUsers(users=loaded_pack.test_users),
            content_path=content,
            config=load_config(config),
            strict=strict,
            dry_run=dry_run,
            no_network=no_network,
            timeout_seconds=request_timeout_seconds,
            now=now,
        )
        write_results_json(output_results, results, redact=redact)
        write_samples_csv(output_samples, results, redact=redact)
        typer.echo(f"aggregate status: {results.aggregate_status}")
        if results.decision:
            typer.echo(f"release decision: {results.decision.get('release_decision')}")
        if results.aggregate_status == "FAIL":
            raise typer.Exit(2)
        if results.aggregate_status == "REVIEW" and fail_on_review:
            raise typer.Exit(3)
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("generate-demo-fixtures")
def generate_demo_fixtures_command(
    output_dir: Path = typer.Option(..., "--output-dir", file_okay=False, dir_okay=True),
    users: int = typer.Option(4, "--users", min=2),
    documents: int = typer.Option(20, "--documents", min=8),
    seed: int = typer.Option(1, "--seed"),
    force: bool = typer.Option(False, "--force"),
    now: str | None = typer.Option(None, "--now"),
) -> None:
    try:
        outputs = generate_demo_fixtures_impl(output_dir, users, documents, seed, force, now)
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    for name, path in outputs.items():
        typer.echo(f"{name}={path}")
    quality = json.loads(Path(outputs["fixture_quality_json"]).read_text(encoding="utf-8"))
    typer.echo(f"fixture quality: {quality['quality_grade']}")


@app.command("run-demo")
def run_demo_command(
    output_dir: Path = typer.Option(..., "--output-dir", file_okay=False, dir_okay=True),
    mode: str = typer.Option("safe", "--mode"),
    users: int = typer.Option(4, "--users", min=2),
    documents: int = typer.Option(20, "--documents", min=8),
    seed: int = typer.Option(1, "--seed"),
    force: bool = typer.Option(False, "--force"),
    now: str | None = typer.Option(None, "--now"),
) -> None:
    try:
        outputs = run_demo_impl(output_dir, mode, users, documents, seed, force, now)
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    for name, path in outputs.items():
        typer.echo(f"{name}={path}")
    results_key = "results"
    if results_key in outputs:
        result_data = json.loads(Path(outputs[results_key]).read_text(encoding="utf-8"))
        typer.echo(f"aggregate status: {result_data['aggregate_status']}")
        typer.echo(f"release decision: {result_data.get('decision', {}).get('release_decision')}")


@app.command("report")
def report_command(
    results: Path = typer.Option(..., "--results"),
    output_report: Path = typer.Option(..., "--output-report"),
    output_junit: Path = typer.Option(..., "--output-junit"),
    fail_on_review: bool = typer.Option(False, "--fail-on-review"),
) -> None:
    try:
        loaded = load_results(results)
        write_markdown_report(output_report, loaded)
        write_junit(output_junit, loaded, fail_on_review=fail_on_review)
        typer.echo("report written")
    except Exception as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("handoff-bundle")
def handoff_bundle_command(
    output_zip: Path = typer.Option(..., "--output-zip"),
    pack: Path | None = typer.Option(None, "--pack"),
    queries: Path | None = typer.Option(None, "--queries"),
    results: Path | None = typer.Option(None, "--results"),
    test_results: Path | None = typer.Option(None, "--test-results"),
    report: Path | None = typer.Option(None, "--report"),
    junit: Path | None = typer.Option(None, "--junit"),
    fixture_quality: Path | None = typer.Option(None, "--fixture-quality"),
    access_matrix: Path | None = typer.Option(None, "--access-matrix"),
    boundary_coverage: Path | None = typer.Option(None, "--boundary-coverage"),
    endpoint: Path | None = typer.Option(None, "--endpoint"),
    config: Path | None = typer.Option(None, "--config"),
) -> None:
    files = {
        "pack/canary_pack.yml": pack,
        "pack/canary_queries.csv": queries,
        "results/results.json": results,
        "results/test_results.csv": test_results,
        "results/permission_regression_report.md": report,
        "results/junit.xml": junit,
        "quality/fixture_quality.json": fixture_quality,
        "coverage/access_matrix.csv": access_matrix,
        "coverage/boundary_coverage.csv": boundary_coverage,
        "endpoint/endpoint.yml": endpoint,
        "config/thresholds.yml": config,
    }
    manifest = create_handoff_bundle(output_zip, files)
    typer.echo(f"wrote {output_zip}")
    typer.echo(f"files={len(manifest['files'])}")


if __name__ == "__main__":
    app()
