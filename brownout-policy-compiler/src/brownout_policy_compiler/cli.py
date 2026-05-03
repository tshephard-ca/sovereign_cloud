from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .compile_rules import CompileOptions, compile_from_paths
from .config import load_config
from .data_generator import generate_realistic_bundle
from .event_schema import load_event, validate_event
from .policy_pack import load_policy_pack
from .report import write_markdown_summary
from .service_priority import load_service_priority, validate_service_priority
from .workflows import (
    run_tabletop,
    write_approval_matrix_template,
    write_endpoint_inventory_template,
    write_event_scenario,
    write_init_all,
    write_organization_template,
    write_policy_pack_template,
    write_post_incident_diff,
    write_questionnaire,
    write_readiness_from_services,
    write_rollback_controls_template,
    write_scenario_catalog,
    write_services_template,
    write_tabletop_template,
    write_thresholds_template,
    write_trusted_sources_template,
)


app = typer.Typer(help="Compile review-only temporary brownout policy packages.")
init_app = typer.Typer(help="Generate starter input files for service-priority review.")
generate_app = typer.Typer(help="Generate deterministic offline scenarios and worksheets.")
lab_app = typer.Typer(help="Generate and audit deterministic lab/demo bundles.")
app.add_typer(init_app, name="init")
app.add_typer(generate_app, name="generate")
app.add_typer(lab_app, name="lab")


@init_app.command("all")
def init_all(
    output_dir: Path = typer.Option(Path("out/input_seed"), "--output-dir"),
) -> None:
    """Write a complete deterministic input seed bundle."""
    paths = write_init_all(output_dir)
    typer.echo(f"wrote input seed bundle: {output_dir}")
    typer.echo(f"service-priority file: {paths['service_priority']}")
    typer.echo(f"event scenarios: {paths['events']}")


@init_app.command("organization")
def init_organization(
    output: Path = typer.Option(Path("out/input_seed/organization.yml"), "--output"),
) -> None:
    """Write a starter organization profile."""
    write_organization_template(output)
    typer.echo(f"wrote organization profile: {output}")


@init_app.command("services")
def init_services(
    output: Path = typer.Option(Path("out/input_seed/service_priority.yml"), "--output"),
) -> None:
    """Write a complete starter service-priority YAML file."""
    write_services_template(output)
    typer.echo(f"wrote service-priority file: {output}")


@init_app.command("trusted-sources")
def init_trusted_sources(
    output: Path = typer.Option(Path("out/input_seed/trusted_sources.yml"), "--output"),
) -> None:
    """Write starter trusted source groups."""
    write_trusted_sources_template(output)
    typer.echo(f"wrote trusted source groups: {output}")


@init_app.command("endpoints")
def init_endpoints(
    output: Path = typer.Option(Path("out/input_seed/endpoint_inventory.csv"), "--output"),
) -> None:
    """Write a starter endpoint inventory CSV."""
    write_endpoint_inventory_template(output)
    typer.echo(f"wrote endpoint inventory: {output}")


@init_app.command("approvals")
def init_approvals(
    output: Path = typer.Option(Path("out/input_seed/approval_matrix.yml"), "--output"),
) -> None:
    """Write a starter approval matrix."""
    write_approval_matrix_template(output)
    typer.echo(f"wrote approval matrix: {output}")


@init_app.command("rollback-controls")
def init_rollback_controls(
    output: Path = typer.Option(Path("out/input_seed/rollback_controls.yml"), "--output"),
) -> None:
    """Write starter rollback controls."""
    write_rollback_controls_template(output)
    typer.echo(f"wrote rollback controls: {output}")


@init_app.command("policy-pack")
def init_policy_pack(
    output: Path = typer.Option(Path("out/input_seed/policy_pack.yml"), "--output"),
) -> None:
    """Write a starter conservative policy pack."""
    write_policy_pack_template(output)
    typer.echo(f"wrote policy pack: {output}")


@init_app.command("thresholds")
def init_thresholds(
    output: Path = typer.Option(Path("out/input_seed/thresholds.yml"), "--output"),
) -> None:
    """Write a starter thresholds config."""
    write_thresholds_template(output)
    typer.echo(f"wrote thresholds config: {output}")


@init_app.command("questionnaire")
def init_questionnaire(
    output: Path = typer.Option(Path("out/input_seed/service_priority_questions.md"), "--output"),
) -> None:
    """Write a service-priority questionnaire."""
    write_questionnaire(output)
    typer.echo(f"wrote service-priority questionnaire: {output}")


@generate_app.command("bundle")
def generate_bundle(
    output_dir: Path = typer.Option(Path("examples/generated/full_coverage"), "--output-dir"),
    include_outputs: bool = typer.Option(True, "--include-outputs/--inputs-only"),
) -> None:
    """Compatibility alias for lab generate-bundle."""
    coverage = generate_realistic_bundle(output_dir, include_outputs=include_outputs)
    typer.echo(f"generated lab bundle: {output_dir}")
    typer.echo(f"input scenarios: {coverage['input']['scenario_count']}")
    if include_outputs:
        typer.echo(f"compiled scenarios: {coverage['output']['scenario_outputs']}")
        typer.echo(f"generated actions: {coverage['output']['action_count']}")
        typer.echo(f"identified gaps: {len(coverage['gaps'])}")


@lab_app.command("generate-bundle")
def lab_generate_bundle(
    output_dir: Path = typer.Option(Path("examples/generated/full_coverage"), "--output-dir"),
    include_outputs: bool = typer.Option(True, "--include-outputs/--inputs-only"),
) -> None:
    """Generate deterministic lab data and optional compiled review packages."""
    coverage = generate_realistic_bundle(output_dir, include_outputs=include_outputs)
    typer.echo(f"generated lab bundle: {output_dir}")
    typer.echo(f"input scenarios: {coverage['input']['scenario_count']}")
    if include_outputs:
        typer.echo(f"compiled scenarios: {coverage['output']['scenario_outputs']}")
        typer.echo(f"generated actions: {coverage['output']['action_count']}")
        typer.echo(f"identified gaps: {len(coverage['gaps'])}")


@generate_app.command("event")
def generate_event(
    scenario: str = typer.Option("01_volumetric_public_and_vpn", "--scenario"),
    output: Path = typer.Option(Path("out/input_seed/ddos_event.json"), "--output"),
) -> None:
    """Write one deterministic normalized DDoS mitigation event scenario."""
    try:
        selected = write_event_scenario(scenario, output)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"wrote event scenario: {output}")
    typer.echo(f"scenario: {Path(selected.file_name).stem}")


@generate_app.command("scenario-catalog")
def generate_scenario_catalog(
    output: Path = typer.Option(Path("out/input_seed/scenario_catalog.json"), "--output"),
) -> None:
    """Write the deterministic scenario catalog."""
    write_scenario_catalog(output)
    typer.echo(f"wrote scenario catalog: {output}")


@generate_app.command("tabletop")
def generate_tabletop(
    output: Path = typer.Option(Path("out/input_seed/tabletop_worksheet.md"), "--output"),
) -> None:
    """Write a tabletop worksheet for the deterministic scenarios."""
    write_tabletop_template(output)
    typer.echo(f"wrote tabletop worksheet: {output}")


@app.command()
def compile(
    event: Path = typer.Option(..., "--event", exists=True, readable=True),
    services: Path = typer.Option(..., "--services", exists=True, readable=True),
    output_plan: Path = typer.Option(..., "--output-plan"),
    output_actions: Path = typer.Option(..., "--output-actions"),
    output_rollback: Path = typer.Option(..., "--output-rollback"),
    summary: Path = typer.Option(..., "--summary"),
    config: Optional[Path] = typer.Option(None, "--config", exists=True, readable=True),
    policy_pack: Optional[Path] = typer.Option(None, "--policy-pack", exists=True, readable=True),
    incident_id: Optional[str] = typer.Option(None, "--incident-id"),
    now: Optional[str] = typer.Option(None, "--now"),
    strict: bool = typer.Option(False, "--strict"),
    redact: bool = typer.Option(False, "--redact"),
    allow_null_route: bool = typer.Option(False, "--allow-null-route"),
    allow_source_blocks: bool = typer.Option(False, "--allow-source-blocks"),
    allow_admin_lockdown: bool = typer.Option(False, "--allow-admin-lockdown"),
    max_actions: Optional[int] = typer.Option(None, "--max-actions"),
    decision_brief: Optional[Path] = typer.Option(None, "--decision-brief", help="Decision brief JSON path. Defaults next to --summary."),
    decision_brief_markdown: Optional[Path] = typer.Option(None, "--decision-brief-markdown", help="Decision brief Markdown path. Defaults next to --summary."),
    operator_queue: Optional[Path] = typer.Option(None, "--operator-queue", help="Operator queue CSV path. Defaults next to --summary."),
    approval_queue: Optional[Path] = typer.Option(None, "--approval-queue", help="Approval queue CSV path. Defaults next to --summary."),
    rollback_clock: Optional[Path] = typer.Option(None, "--rollback-clock", help="Rollback clock JSON path. Defaults next to --summary."),
    blocked_actions: Optional[Path] = typer.Option(None, "--blocked-actions", help="Blocked actions JSON path. Defaults next to --summary."),
    fail_on_fail_status: bool = typer.Option(False, "--fail-on-fail-status"),
) -> None:
    """Compile a normalized event and service-priority file into a review package."""
    try:
        result = compile_from_paths(
            CompileOptions(
                event_path=event,
                services_path=services,
                output_plan=output_plan,
                output_actions=output_actions,
                output_rollback=output_rollback,
                summary=summary,
                config_path=config,
                policy_pack_path=policy_pack,
                incident_id=incident_id,
                now=now,
                strict=strict,
                redact=redact,
                allow_null_route=allow_null_route,
                allow_source_blocks=allow_source_blocks,
                allow_admin_lockdown=allow_admin_lockdown,
                max_actions=max_actions,
                decision_brief=decision_brief,
                decision_brief_markdown=decision_brief_markdown,
                operator_queue=operator_queue,
                approval_queue=approval_queue,
                rollback_clock=rollback_clock,
                blocked_actions=blocked_actions,
            )
        )
    except Exception as exc:
        raise typer.Exit(code=1) from exc
    for warning in result.warnings:
        typer.echo(f"warning: {warning}", err=True)
    for blocker in result.blockers:
        typer.echo(f"blocker: {blocker}", err=True)
    typer.echo(f"review package status: {result.summary.lint_status}")
    if fail_on_fail_status and result.summary.lint_status == "FAIL":
        raise typer.Exit(code=2)


@app.command()
def validate(
    event: Path = typer.Option(..., "--event", exists=True, readable=True),
    services: Path = typer.Option(..., "--services", exists=True, readable=True),
    config: Optional[Path] = typer.Option(None, "--config", exists=True, readable=True),
    policy_pack: Optional[Path] = typer.Option(None, "--policy-pack", exists=True, readable=True),
    strict: bool = typer.Option(False, "--strict"),
) -> None:
    """Validate event, service-priority, config, and optional policy pack inputs."""
    compiler_config = load_config(config)
    event_model = load_event(event)
    services_model = load_service_priority(services)
    pack, pack_validation, _ = load_policy_pack(policy_pack)
    event_validation = validate_event(event_model, strict=strict)
    service_validation = validate_service_priority(
        services_model,
        strict=strict,
        fail_on_p0_shed=compiler_config.fail_on_p0_shed,
    )
    warnings = sorted(set(event_validation.warnings + service_validation.warnings + pack_validation.warnings))
    blockers = sorted(set(event_validation.blockers + service_validation.blockers + pack_validation.blockers))
    for warning in warnings:
        typer.echo(f"warning: {warning}", err=True)
    for blocker in blockers:
        typer.echo(f"blocker: {blocker}", err=True)
    if pack is None or blockers or (strict and warnings):
        raise typer.Exit(code=1)
    typer.echo("validation status: PASS")


@app.command()
def explain(
    plan: Path = typer.Option(..., "--plan", exists=True, readable=True),
    output_markdown: Path = typer.Option(..., "--output-markdown"),
) -> None:
    """Write a markdown summary from a brownout plan."""
    write_markdown_summary(plan, output_markdown)
    typer.echo(f"wrote markdown summary: {output_markdown}")


@app.command("generate-data")
def generate_data(
    output_dir: Path = typer.Option(Path("examples/generated/full_coverage"), "--output-dir"),
    include_outputs: bool = typer.Option(True, "--include-outputs/--inputs-only"),
) -> None:
    """Compatibility alias for lab generate-bundle."""
    coverage = generate_realistic_bundle(output_dir, include_outputs=include_outputs)
    typer.echo(f"generated data bundle: {output_dir}")
    typer.echo(f"input scenarios: {coverage['input']['scenario_count']}")
    if include_outputs:
        typer.echo(f"compiled scenarios: {coverage['output']['scenario_outputs']}")
        typer.echo(f"generated actions: {coverage['output']['action_count']}")
        typer.echo(f"identified gaps: {len(coverage['gaps'])}")


@app.command()
def readiness(
    services: Path = typer.Option(..., "--services", exists=True, readable=True),
    output: Path = typer.Option(Path("out/readiness_report.json"), "--output"),
) -> None:
    """Score service-priority input readiness before an incident."""
    report = write_readiness_from_services(services, output)
    typer.echo(f"wrote readiness report: {output}")
    typer.echo(f"readiness status: {report['status']}")
    typer.echo(f"readiness score: {report['review_package_readiness_score']}")


@app.command()
def tabletop(
    event: Path = typer.Option(..., "--event", exists=True, readable=True),
    services: Path = typer.Option(..., "--services", exists=True, readable=True),
    output_dir: Path = typer.Option(Path("out/tabletop_run"), "--output-dir"),
    config: Optional[Path] = typer.Option(None, "--config", exists=True, readable=True),
    policy_pack: Optional[Path] = typer.Option(None, "--policy-pack", exists=True, readable=True),
    incident_id: Optional[str] = typer.Option(None, "--incident-id"),
    now: Optional[str] = typer.Option(None, "--now"),
    allow_null_route: bool = typer.Option(False, "--allow-null-route"),
    allow_source_blocks: bool = typer.Option(False, "--allow-source-blocks"),
    allow_admin_lockdown: bool = typer.Option(False, "--allow-admin-lockdown"),
    max_actions: Optional[int] = typer.Option(None, "--max-actions"),
) -> None:
    """Compile a tabletop run bundle with a markdown review report."""
    paths = run_tabletop(
        event_path=event,
        services_path=services,
        output_dir=output_dir,
        config_path=config,
        policy_pack_path=policy_pack,
        incident_id=incident_id,
        now=now,
        allow_null_route=allow_null_route,
        allow_source_blocks=allow_source_blocks,
        allow_admin_lockdown=allow_admin_lockdown,
        max_actions=max_actions,
    )
    typer.echo(f"wrote tabletop run: {output_dir}")
    typer.echo(f"tabletop report: {paths['report']}")


@app.command("post-incident-diff")
def post_incident_diff(
    plan: Path = typer.Option(..., "--plan", exists=True, readable=True),
    actual_changes: Path = typer.Option(..., "--actual-changes", exists=True, readable=True),
    output: Path = typer.Option(Path("out/post_incident_diff.json"), "--output"),
) -> None:
    """Compare intended brownout candidates with operator-entered actual changes."""
    diff = write_post_incident_diff(plan, actual_changes, output)
    typer.echo(f"wrote post-incident diff: {output}")
    typer.echo(f"post-incident diff status: {diff['status']}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
