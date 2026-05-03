from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from .bundles import (
    apply_rate_cards,
    bundle_paths,
    init_bundle as init_input_bundle,
    validate_bundle as validate_input_bundle,
    write_decision_bundle,
    write_generated_constraints,
    write_simulated_endpoints,
)
from .config import load_config
from .constraints import load_constraints
from .endpoint_profile import load_endpoint_profiles
from .http_client import load_results_json, run_benchmark_plan, write_results_json
from .io_outputs import write_samples_csv
from .models import EndpointProfiles
from .plan import build_plan, load_plan, write_plan
from .prompt_packs import canonical_pack_name, write_prompt_pack
from .recommendation import build_recommendation, write_recommendation_json
from .report import render_executive_summary, render_markdown_report, write_report
from .workload_profile import load_workload_profile

app = typer.Typer(no_args_is_help=True)


@app.command()
def validate(
    workload: str | None = typer.Option(None, "--workload"),
    endpoints: str | None = typer.Option(None, "--endpoints"),
    constraints: str | None = typer.Option(None, "--constraints"),
    bundle: str | None = typer.Option(None, "--bundle"),
    config: str | None = typer.Option(None, "--config"),
    strict: bool = typer.Option(False, "--strict"),
    redact: bool = typer.Option(False, "--redact"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    no_network: bool = typer.Option(False, "--no-network"),
    max_requests: int | None = typer.Option(None, "--max-requests"),
    warmup_requests: int | None = typer.Option(None, "--warmup-requests"),
    concurrency: int | None = typer.Option(None, "--concurrency"),
    request_timeout_seconds: float | None = typer.Option(None, "--request-timeout-seconds"),
    now: str | None = typer.Option(None, "--now"),
) -> None:
    _ = no_network
    try:
        workload, endpoints, constraints, config, base_dir = _resolve_inputs(bundle, workload, endpoints, constraints, config)
        cfg = load_config(config)
        workload_profile = load_workload_profile(workload)
        endpoint_profiles = _load_endpoint_profiles(endpoints, bundle)
        constraint_profile = load_constraints(constraints)
        plan = build_plan(
            workload_profile,
            endpoint_profiles,
            constraint_profile,
            cfg,
            base_dir=base_dir,
            now=now,
            max_requests=max_requests,
            warmup_requests=warmup_requests,
            concurrency=concurrency,
            request_timeout_seconds=request_timeout_seconds,
            strict=strict,
            redact=redact,
            dry_run=dry_run,
        )
        if strict and not any(endpoint.eligible for endpoint in plan.endpoints):
            raise RuntimeError("NO_ELIGIBLE_ENDPOINTS")
        typer.echo("VALID")
        for warning in plan.warnings:
            typer.echo(f"warning: {warning}", err=True)
    except Exception as exc:
        typer.echo(f"INVALID: {exc}", err=True)
        raise typer.Exit(1)


@app.command()
def plan(
    workload: str | None = typer.Option(None, "--workload"),
    endpoints: str | None = typer.Option(None, "--endpoints"),
    constraints: str | None = typer.Option(None, "--constraints"),
    bundle: str | None = typer.Option(None, "--bundle"),
    output_plan: str = typer.Option(..., "--output-plan"),
    config: str | None = typer.Option(None, "--config"),
    strict: bool = typer.Option(False, "--strict"),
    redact: bool = typer.Option(False, "--redact"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    no_network: bool = typer.Option(False, "--no-network"),
    max_requests: int | None = typer.Option(None, "--max-requests"),
    warmup_requests: int | None = typer.Option(None, "--warmup-requests"),
    concurrency: int | None = typer.Option(None, "--concurrency"),
    request_timeout_seconds: float | None = typer.Option(None, "--request-timeout-seconds"),
    now: str | None = typer.Option(None, "--now"),
) -> None:
    _ = no_network
    workload, endpoints, constraints, config, base_dir = _resolve_inputs(bundle, workload, endpoints, constraints, config)
    cfg = load_config(config)
    workload_profile = load_workload_profile(workload)
    endpoint_profiles = _load_endpoint_profiles(endpoints, bundle)
    constraint_profile = load_constraints(constraints)
    built = build_plan(
        workload_profile,
        endpoint_profiles,
        constraint_profile,
        cfg,
        base_dir=base_dir,
        now=now,
        max_requests=max_requests,
        warmup_requests=warmup_requests,
        concurrency=concurrency,
        request_timeout_seconds=request_timeout_seconds,
        strict=strict,
        redact=redact,
        dry_run=dry_run,
    )
    if strict and not any(endpoint.eligible for endpoint in built.endpoints):
        typer.echo("NO_ELIGIBLE_ENDPOINTS", err=True)
        raise typer.Exit(1)
    write_plan(built, output_plan)
    typer.echo(output_plan)


@app.command()
def run(
    plan: str = typer.Option(..., "--plan"),
    output_results: str = typer.Option(..., "--output-results"),
    output_samples: str = typer.Option(..., "--output-samples"),
    config: str | None = typer.Option(None, "--config"),
    strict: bool = typer.Option(False, "--strict"),
    redact: bool = typer.Option(False, "--redact"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    no_network: bool = typer.Option(False, "--no-network"),
    max_requests: int | None = typer.Option(None, "--max-requests"),
    warmup_requests: int | None = typer.Option(None, "--warmup-requests"),
    concurrency: int | None = typer.Option(None, "--concurrency"),
    request_timeout_seconds: float | None = typer.Option(None, "--request-timeout-seconds"),
    now: str | None = typer.Option(None, "--now"),
) -> None:
    _ = (max_requests, warmup_requests, concurrency, request_timeout_seconds)
    cfg = load_config(config)
    benchmark_plan = load_plan(plan)
    if strict and not any(endpoint.eligible for endpoint in benchmark_plan.endpoints):
        typer.echo("NO_ELIGIBLE_ENDPOINTS", err=True)
        raise typer.Exit(1)
    try:
        results = run_benchmark_plan(
            benchmark_plan,
            cfg,
            dry_run=dry_run,
            no_network=no_network,
            strict=strict,
            redact=redact,
            now=now,
        )
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    write_results_json(results, output_results)
    write_samples_csv(results.samples, output_samples)
    typer.echo(output_results)


@app.command()
def recommend(
    results: str = typer.Option(..., "--results"),
    constraints: str | None = typer.Option(None, "--constraints"),
    bundle: str | None = typer.Option(None, "--bundle"),
    output_recommendation: str | None = typer.Option(None, "--output-recommendation"),
    output_report: str | None = typer.Option(None, "--output-report"),
    output_bundle: str | None = typer.Option(None, "--output-bundle"),
    config: str | None = typer.Option(None, "--config"),
    strict: bool = typer.Option(False, "--strict"),
    redact: bool = typer.Option(False, "--redact"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    no_network: bool = typer.Option(False, "--no-network"),
    max_requests: int | None = typer.Option(None, "--max-requests"),
    warmup_requests: int | None = typer.Option(None, "--warmup-requests"),
    concurrency: int | None = typer.Option(None, "--concurrency"),
    request_timeout_seconds: float | None = typer.Option(None, "--request-timeout-seconds"),
    now: str | None = typer.Option(None, "--now"),
) -> None:
    _ = (strict, redact, dry_run, no_network, max_requests, warmup_requests, concurrency, request_timeout_seconds, now)
    if bundle:
        paths = bundle_paths(bundle)
        constraints = constraints or str(paths["constraints"])
        config = config or str(paths["thresholds"])
    if constraints is None:
        typer.echo("--constraints or --bundle is required", err=True)
        raise typer.Exit(1)
    if output_bundle is None and (output_recommendation is None or output_report is None):
        typer.echo("--output-recommendation and --output-report are required unless --output-bundle is used", err=True)
        raise typer.Exit(1)
    cfg = load_config(config)
    benchmark_results = load_results_json(results)
    constraint_profile = load_constraints(constraints)
    recommendation = build_recommendation(benchmark_results, constraint_profile, cfg)
    if output_bundle:
        recommendation_json = json.dumps(recommendation.model_dump(mode="json"), indent=2, sort_keys=False) + "\n"
        recommendation_markdown = render_markdown_report(recommendation)
        write_decision_bundle(
            output_bundle,
            input_bundle=bundle,
            results_path=results,
            recommendation_json=recommendation_json,
            recommendation_markdown=recommendation_markdown,
            executive_summary_markdown=render_executive_summary(recommendation),
        )
        typer.echo(output_bundle)
        return
    assert output_recommendation is not None
    assert output_report is not None
    write_recommendation_json(recommendation, output_recommendation)
    write_report(recommendation, output_report)
    typer.echo(output_recommendation)


@app.command()
def evaluate(
    workload: str | None = typer.Option(None, "--workload"),
    endpoints: str | None = typer.Option(None, "--endpoints"),
    constraints: str | None = typer.Option(None, "--constraints"),
    bundle: str | None = typer.Option(None, "--bundle"),
    output_bundle: str | None = typer.Option(None, "--output-bundle"),
    output_plan: str | None = typer.Option(None, "--output-plan"),
    output_results: str | None = typer.Option(None, "--output-results"),
    output_samples: str | None = typer.Option(None, "--output-samples"),
    output_recommendation: str | None = typer.Option(None, "--output-recommendation"),
    output_report: str | None = typer.Option(None, "--output-report"),
    config: str | None = typer.Option(None, "--config"),
    strict: bool = typer.Option(False, "--strict"),
    redact: bool = typer.Option(False, "--redact"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    no_network: bool = typer.Option(False, "--no-network"),
    max_requests: int | None = typer.Option(None, "--max-requests"),
    warmup_requests: int | None = typer.Option(None, "--warmup-requests"),
    concurrency: int | None = typer.Option(None, "--concurrency"),
    request_timeout_seconds: float | None = typer.Option(None, "--request-timeout-seconds"),
    now: str | None = typer.Option(None, "--now"),
) -> None:
    if output_bundle is None and (output_plan is None or output_results is None or output_samples is None or output_recommendation is None or output_report is None):
        typer.echo(
            "--output-bundle is required unless --output-plan, --output-results, --output-samples, --output-recommendation, and --output-report are supplied",
            err=True,
        )
        raise typer.Exit(1)

    workload, endpoints, constraints, config, base_dir = _resolve_inputs(bundle, workload, endpoints, constraints, config)
    cfg = load_config(config)
    output_root = Path(output_bundle) if output_bundle else None
    artifact_root = (output_root / "run_artifacts") if output_root else None
    plan_path = Path(output_plan) if output_plan else artifact_root / "benchmark_plan.yml"  # type: ignore[operator]
    results_path = Path(output_results) if output_results else artifact_root / "results.json"  # type: ignore[operator]
    samples_path = Path(output_samples) if output_samples else artifact_root / "samples.csv"  # type: ignore[operator]

    workload_profile = load_workload_profile(workload)
    endpoint_profiles = _load_endpoint_profiles(endpoints, bundle)
    constraint_profile = load_constraints(constraints)
    built = build_plan(
        workload_profile,
        endpoint_profiles,
        constraint_profile,
        cfg,
        base_dir=base_dir,
        now=now,
        max_requests=max_requests,
        warmup_requests=warmup_requests,
        concurrency=concurrency,
        request_timeout_seconds=request_timeout_seconds,
        strict=strict,
        redact=redact,
        dry_run=dry_run,
    )
    if strict and not any(endpoint.eligible for endpoint in built.endpoints):
        typer.echo("NO_ELIGIBLE_ENDPOINTS", err=True)
        raise typer.Exit(1)
    write_plan(built, str(plan_path))
    try:
        results_obj = run_benchmark_plan(
            built,
            cfg,
            dry_run=dry_run,
            no_network=no_network,
            strict=strict,
            redact=redact,
            now=now,
        )
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    write_results_json(results_obj, str(results_path))
    write_samples_csv(results_obj.samples, str(samples_path))
    recommendation = build_recommendation(results_obj, constraint_profile, cfg)

    if output_bundle:
        recommendation_json = json.dumps(recommendation.model_dump(mode="json"), indent=2, sort_keys=False) + "\n"
        recommendation_markdown = render_markdown_report(recommendation)
        write_decision_bundle(
            output_bundle,
            input_bundle=bundle,
            results_path=results_path,
            recommendation_json=recommendation_json,
            recommendation_markdown=recommendation_markdown,
            executive_summary_markdown=render_executive_summary(recommendation),
        )
        typer.echo(output_bundle)
        return

    assert output_recommendation is not None
    assert output_report is not None
    write_recommendation_json(recommendation, output_recommendation)
    write_report(recommendation, output_report)
    typer.echo(output_recommendation)


@app.command()
def init_bundle(
    template: str = typer.Option("customer-chat", "--template"),
    output: str = typer.Option(..., "--output"),
    prompt_count: int = typer.Option(100, "--prompt-count"),
    seed: int = typer.Option(12345, "--seed"),
) -> None:
    paths = init_input_bundle(output, template=template, prompt_count=prompt_count, seed=seed)
    typer.echo(str(paths["root"]))


@app.command()
def generate_prompts(
    output: str = typer.Option(..., "--output"),
    workload: str | None = typer.Option(None, "--workload"),
    prompt_pack: str | None = typer.Option(None, "--prompt-pack"),
    count: int = typer.Option(100, "--count"),
    seed: int = typer.Option(12345, "--seed"),
) -> None:
    pack = prompt_pack
    if pack is None:
        if workload is None:
            typer.echo("--workload or --prompt-pack is required", err=True)
            raise typer.Exit(1)
        workload_profile = load_workload_profile(workload)
        pack = {
            "chat_text": "customer_chat_short",
            "completion_text": "completion_text",
            "embedding": "embedding_search",
            "classification": "classification",
            "summarization": "summarization_long",
        }.get(workload_profile.workload_type, "customer_chat_short")
    write_prompt_pack(output, canonical_pack_name(pack), count=count, seed=seed)
    typer.echo(output)


@app.command()
def generate_constraints(
    output: str = typer.Option(..., "--output"),
    policy_pack: str = typer.Option("customer-chat", "--policy-pack"),
) -> None:
    write_generated_constraints(output, policy_pack=policy_pack)
    typer.echo(output)


@app.command()
def validate_bundle(
    input: str = typer.Option(..., "--input"),
    strict: bool = typer.Option(False, "--strict"),
) -> None:
    errors, warnings = validate_input_bundle(input)
    for warning in warnings:
        typer.echo(f"warning: {warning}", err=True)
    if errors or (strict and warnings):
        for error in errors:
            typer.echo(f"error: {error}", err=True)
        raise typer.Exit(1)
    typer.echo("VALID_BUNDLE")


@app.command()
def simulate(
    bundle: str = typer.Option(..., "--bundle"),
    output: str = typer.Option(..., "--output"),
) -> None:
    write_simulated_endpoints(bundle, output)
    typer.echo(output)


def _resolve_inputs(
    bundle: str | None,
    workload: str | None,
    endpoints: str | None,
    constraints: str | None,
    config: str | None,
) -> tuple[str, str, str, str | None, str]:
    base_dir = "."
    if bundle:
        paths = bundle_paths(bundle)
        workload = workload or str(paths["workload"])
        endpoints = endpoints or str(paths["endpoints"])
        constraints = constraints or str(paths["constraints"])
        config = config or str(paths["thresholds"])
        base_dir = str(paths["root"])
    if workload is None or endpoints is None or constraints is None:
        raise ValueError("--workload, --endpoints, and --constraints are required unless --bundle is used")
    return workload, endpoints, constraints, config, base_dir


def _load_endpoint_profiles(endpoints: str, bundle: str | None) -> EndpointProfiles:
    endpoint_profiles = load_endpoint_profiles(endpoints)
    if bundle:
        rate_cards = bundle_paths(bundle)["rate_cards"]
        if rate_cards.exists():
            return apply_rate_cards(endpoint_profiles, rate_cards)
    return endpoint_profiles


def main() -> None:
    app()


if __name__ == "__main__":
    sys.exit(main())
