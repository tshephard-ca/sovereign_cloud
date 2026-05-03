from __future__ import annotations

from pathlib import Path

import typer
import yaml

from .baseline import compare_baseline, create_baseline
from .business_impact import build_business_impact_report, write_business_impact_json, write_business_impact_markdown
from .collect_local import collect_local as collect_local_impl
from .coverage_report import build_coverage_report, write_coverage_json, write_coverage_markdown
from .evidence_loader import load_evidence
from .fixtures import generate_fixtures as generate_fixtures_impl
from .handoff import create_handoff_bundle
from .importers import import_bmc_snapshot as import_bmc_snapshot_impl
from .node_inventory import load_node_inventory
from .planning import generate_pairwise_plan as generate_pairwise_plan_impl
from .planning import import_inventory_csv as import_inventory_csv_impl
from .planning import render_sbatch_template
from .portfolio import build_portfolio, write_portfolio_json, write_portfolio_markdown
from .qualification_policy import load_policy
from .report import build_summary, write_labels_csv, write_markdown_report, write_quarantine_csv, write_summary_json
from .runtime_guard import run_runtime_guard
from .rules import qualify_nodes
from .runbook import load_runbook, output_from_runbook, value_from_runbook
from .schema_validation import validate_artifacts
from .simulation import simulate_policies, write_simulation_csv, write_simulation_json
from .slurm_render import render_drain_review, render_slurm_fragment
from .workflow import qualify_workflow

app = typer.Typer(help="Convert GPU qualification evidence into review-only Slurm labels and quarantine recommendations.")


@app.command("validate-evidence")
def validate_evidence(
    evidence: Path = typer.Option(..., "--evidence", exists=False, file_okay=False, dir_okay=True),
    policy: Path | None = typer.Option(None, "--policy", exists=False, file_okay=True, dir_okay=False),
    node_inventory: Path | None = typer.Option(None, "--node-inventory", exists=False, file_okay=True, dir_okay=False),
    schemas_dir: Path | None = typer.Option(Path("schemas"), "--schemas-dir", exists=False, file_okay=False, dir_okay=True),
    strict: bool = typer.Option(False, "--strict"),
) -> None:
    qualification_policy = _load_policy_or_exit(policy, strict)
    inventory = _load_inventory_or_exit(node_inventory, strict)
    schema_errors = validate_artifacts(schemas_dir=schemas_dir if schemas_dir and schemas_dir.exists() else None, policy=policy, inventory=node_inventory)
    if schema_errors and strict:
        for error in schema_errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(2)
    for error in schema_errors:
        typer.echo(f"WARNING: {error}", err=True)
    nodes = load_evidence(evidence, qualification_policy)
    _validate_inputs(evidence, nodes, qualification_policy, inventory, strict)
    typer.echo(f"nodes_seen={len(nodes)}")
    for warning in _non_strict_warnings(nodes, qualification_policy):
        typer.echo(f"WARNING: {warning}", err=True)


@app.command("qualify")
def qualify(
    evidence: Path | None = typer.Option(None, "--evidence", exists=False, file_okay=False, dir_okay=True),
    node_inventory: Path | None = typer.Option(None, "--node-inventory", exists=False, file_okay=True, dir_okay=False),
    policy: Path | None = typer.Option(None, "--policy", exists=False, file_okay=True, dir_okay=False),
    output_labels: Path | None = typer.Option(None, "--output-labels"),
    output_quarantine: Path | None = typer.Option(None, "--output-quarantine"),
    output_review_queue: Path | None = typer.Option(None, "--output-review-queue"),
    output_slurm_fragment: Path | None = typer.Option(None, "--output-slurm-fragment"),
    output_drain_review: Path | None = typer.Option(None, "--output-drain-review"),
    summary: Path | None = typer.Option(None, "--summary"),
    evidence_bundle: Path | None = typer.Option(None, "--evidence-bundle"),
    business_assumptions: Path | None = typer.Option(None, "--business-assumptions"),
    runbook: Path | None = typer.Option(None, "--runbook", exists=False, file_okay=True, dir_okay=False),
    strict: bool = typer.Option(False, "--strict"),
    redact: bool = typer.Option(False, "--redact"),
) -> None:
    runbook_data = load_runbook(runbook)
    evidence = value_from_runbook(runbook_data, "evidence", evidence)
    node_inventory = value_from_runbook(runbook_data, "node_inventory", node_inventory)
    policy = value_from_runbook(runbook_data, "policy", policy)
    business_assumptions = value_from_runbook(runbook_data, "business_assumptions", business_assumptions)
    output_labels = output_from_runbook(runbook_data, "labels", output_labels)
    output_quarantine = output_from_runbook(runbook_data, "quarantine", output_quarantine)
    output_review_queue = output_from_runbook(runbook_data, "review_queue", output_review_queue)
    output_slurm_fragment = output_from_runbook(runbook_data, "slurm_fragment", output_slurm_fragment)
    output_drain_review = output_from_runbook(runbook_data, "drain_review", output_drain_review)
    summary = output_from_runbook(runbook_data, "summary", summary)
    evidence_bundle = output_from_runbook(runbook_data, "evidence_bundle", evidence_bundle)
    _require_paths(
        {
            "evidence": evidence,
            "output-labels": output_labels,
            "output-quarantine": output_quarantine,
            "output-slurm-fragment": output_slurm_fragment,
            "output-drain-review": output_drain_review,
            "summary": summary,
        }
    )
    qualification_policy = _load_policy_or_exit(policy, strict)
    inventory = _load_inventory_or_exit(node_inventory, strict)
    nodes = load_evidence(evidence, qualification_policy)
    _validate_inputs(evidence, nodes, qualification_policy, inventory, strict)
    result = qualify_workflow(
        evidence=evidence,
        node_inventory=node_inventory,
        policy=policy,
        output_labels=output_labels,
        output_quarantine=output_quarantine,
        output_review_queue=output_review_queue,
        output_slurm_fragment=output_slurm_fragment,
        output_drain_review=output_drain_review,
        summary=summary,
        evidence_bundle=evidence_bundle,
        business_assumptions=business_assumptions,
        strict=strict,
        redact=redact,
        policy_loader=lambda _: qualification_policy,
        inventory_loader=lambda _: inventory,
    )
    for warning in _non_strict_warnings(nodes, qualification_policy):
        typer.echo(f"WARNING: {warning}", err=True)
    typer.echo(f"wrote {output_labels}")
    typer.echo(f"wrote {output_quarantine}")
    typer.echo(f"wrote {result['outputs']['review_queue_csv']}")
    typer.echo(f"wrote {output_slurm_fragment}")
    typer.echo(f"wrote {output_drain_review}")
    typer.echo(f"wrote {summary}")
    if evidence_bundle:
        typer.echo(f"wrote {evidence_bundle}")


@app.command("explain")
def explain(
    summary: Path = typer.Option(..., "--summary", exists=True, file_okay=True, dir_okay=False),
    labels: Path = typer.Option(..., "--labels", exists=True, file_okay=True, dir_okay=False),
    quarantine: Path = typer.Option(..., "--quarantine", exists=True, file_okay=True, dir_okay=False),
    output_markdown: Path = typer.Option(..., "--output-markdown"),
) -> None:
    write_markdown_report(summary, labels, quarantine, output_markdown)
    typer.echo(f"wrote {output_markdown}")


@app.command("collect-local")
def collect_local(
    node_name: str = typer.Option(..., "--node-name"),
    output_dir: Path = typer.Option(..., "--output-dir", file_okay=False, dir_okay=True),
    nvidia_smi: Path = typer.Option(Path("/usr/bin/nvidia-smi"), "--nvidia-smi", file_okay=True, dir_okay=False),
    nccl_all_reduce: Path | None = typer.Option(None, "--nccl-all-reduce", file_okay=True, dir_okay=False),
    run_single_node_nccl: bool = typer.Option(False, "--run-single-node-nccl"),
    timeout_seconds: int = typer.Option(300, "--timeout-seconds"),
) -> None:
    events = collect_local_impl(node_name, output_dir, nvidia_smi, nccl_all_reduce, run_single_node_nccl, timeout_seconds)
    for event in events:
        typer.echo(event)


@app.command("generate-fixtures")
def generate_fixtures(
    output_dir: Path = typer.Option(..., "--output-dir", file_okay=False, dir_okay=True),
    nodes: int = typer.Option(16, "--nodes", min=1),
    gpus_per_node: int = typer.Option(8, "--gpus-per-node", min=1),
    scenario: str = typer.Option("mixed_commissioning", "--scenario"),
    seed: int = typer.Option(1, "--seed"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    try:
        outputs = generate_fixtures_impl(output_dir, nodes, gpus_per_node, scenario, seed, force)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(2) from exc
    for name, path in outputs.items():
        typer.echo(f"{name}={path}")


@app.command("demo")
def demo(
    output_dir: Path = typer.Option(..., "--output-dir", file_okay=False, dir_okay=True),
    nodes: int = typer.Option(64, "--nodes", min=1),
    gpus_per_node: int = typer.Option(8, "--gpus-per-node", min=1),
    scenario: str = typer.Option("mixed_commissioning", "--scenario"),
    seed: int = typer.Option(7, "--seed"),
    hours_at_risk: float = typer.Option(24.0, "--hours-at-risk"),
    accelerator_hour_value: float = typer.Option(3.5, "--accelerator-hour-value"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    try:
        generated = generate_fixtures_impl(output_dir, nodes, gpus_per_node, scenario, seed, force)
        assumptions_path = output_dir / "business_assumptions.yml"
        assumptions_path.write_text(
            yaml.safe_dump(
                {
                    "gpus_per_node": gpus_per_node,
                    "hours_at_risk": hours_at_risk,
                    "accelerator_hour_value": accelerator_hour_value,
                    "release_goal": "multinode_training",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        run_dir = output_dir / "run"
        run = qualify_workflow(
            evidence=generated["evidence"],
            node_inventory=generated["inventory"],
            policy=generated["policy"],
            output_labels=run_dir / "slurm_node_labels.csv",
            output_quarantine=run_dir / "quarantine.csv",
            output_review_queue=run_dir / "review_queue.csv",
            output_slurm_fragment=run_dir / "slurm_features.conf.snippet",
            output_drain_review=run_dir / "drain_review.sh",
            summary=run_dir / "summary.json",
            evidence_bundle=run_dir / "evidence_bundle.json",
            business_assumptions=assumptions_path,
        )
        write_markdown_report(run_dir / "summary.json", run_dir / "slurm_node_labels.csv", run_dir / "quarantine.csv", run_dir / "qualification_summary.md")
        portfolio_data = build_portfolio(run_dir / "summary.json", run_dir / "slurm_node_labels.csv", run_dir / "quarantine.csv")
        write_portfolio_markdown(run_dir / "rack_portfolio.md", portfolio_data)
        write_portfolio_json(run_dir / "rack_portfolio.json", portfolio_data)
        coverage = build_coverage_report(generated["evidence"], run["policy"], run["inventory"], run_dir / "slurm_node_labels.csv", run_dir / "quarantine.csv", run_dir / "summary.json")
        write_coverage_json(run_dir / "coverage.json", coverage)
        write_coverage_markdown(run_dir / "coverage.md", coverage)
        impact = build_business_impact_report(
            run_dir / "summary.json",
            run_dir / "slurm_node_labels.csv",
            run_dir / "quarantine.csv",
            gpus_per_node,
            hours_at_risk,
            accelerator_hour_value,
        )
        write_business_impact_json(run_dir / "business_impact.json", impact)
        write_business_impact_markdown(run_dir / "business_impact.md", impact)
        create_handoff_bundle(
            run_dir / "rackq_handoff.zip",
            {
                "labels/slurm_node_labels.csv": run_dir / "slurm_node_labels.csv",
                "labels/quarantine.csv": run_dir / "quarantine.csv",
                "labels/review_queue.csv": run_dir / "review_queue.csv",
                "slurm/slurm_features.conf.snippet": run_dir / "slurm_features.conf.snippet",
                "slurm/drain_review.sh": run_dir / "drain_review.sh",
                "summary/summary.json": run_dir / "summary.json",
                "summary/qualification_summary.md": run_dir / "qualification_summary.md",
                "policy/qualification_policy.yml": generated["policy"],
                "evidence/evidence_bundle.json": run_dir / "evidence_bundle.json",
            },
            include_dirs={"schemas": Path("schemas"), "docs": Path("docs"), "scripts": Path("scripts")},
        )
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"demo_dir={output_dir}")
    typer.echo(f"run_dir={run_dir}")
    typer.echo(f"nodes_seen={run['summary'].input['nodes_seen']}")
    typer.echo(f"action_queue_nodes={run['summary'].action_queue_counts.get('total', 0)}")


@app.command("generate-pairwise-plan")
def generate_pairwise_plan(
    output_csv: Path = typer.Option(..., "--output-csv"),
    node_inventory: Path | None = typer.Option(None, "--node-inventory", exists=False, file_okay=True, dir_okay=False),
    node_list: str | None = typer.Option(None, "--node-list"),
    strategy: str = typer.Option("pairwise", "--strategy"),
    gpus_per_node: int = typer.Option(8, "--gpus-per-node", min=1),
    message_size_bytes: int = typer.Option(268435456, "--message-size-bytes", min=1),
    max_pairs: int | None = typer.Option(None, "--max-pairs"),
) -> None:
    try:
        rows = generate_pairwise_plan_impl(output_csv, node_inventory, node_list, strategy, gpus_per_node, message_size_bytes, max_pairs)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"wrote {output_csv}")
    typer.echo(f"pairs={len(rows)}")


@app.command("generate-sbatch-template")
def generate_sbatch_template(
    plan_csv: Path = typer.Option(..., "--plan-csv", exists=True, file_okay=True, dir_okay=False),
    output_script: Path = typer.Option(..., "--output-script"),
    nccl_all_reduce: str = typer.Option(..., "--nccl-all-reduce"),
    gpus_per_node: int = typer.Option(8, "--gpus-per-node", min=1),
    time_limit: str = typer.Option("00:30:00", "--time-limit"),
    partition: str | None = typer.Option(None, "--partition"),
) -> None:
    render_sbatch_template(plan_csv, output_script, nccl_all_reduce, gpus_per_node, time_limit, partition)
    typer.echo(f"wrote {output_script}")


@app.command("import-bmc-snapshot")
def import_bmc_snapshot(
    input_json: Path = typer.Option(..., "--input-json", exists=True, file_okay=True, dir_okay=False),
    output_json: Path = typer.Option(..., "--output-json"),
) -> None:
    normalized = import_bmc_snapshot_impl(input_json, output_json)
    typer.echo(f"wrote {output_json}")
    typer.echo(f"sensors={len(normalized['sensors'])}")


@app.command("import-inventory-csv")
def import_inventory_csv(
    input_csv: Path = typer.Option(..., "--input-csv", exists=True, file_okay=True, dir_okay=False),
    output_yml: Path = typer.Option(..., "--output-yml"),
    cluster_id: str | None = typer.Option(None, "--cluster-id"),
    rack_id: str | None = typer.Option(None, "--rack-id"),
) -> None:
    inventory = import_inventory_csv_impl(input_csv, output_yml, cluster_id, rack_id)
    typer.echo(f"wrote {output_yml}")
    typer.echo(f"nodes={len(inventory['nodes'])}")


@app.command("portfolio")
def portfolio(
    summary: Path = typer.Option(..., "--summary", exists=True, file_okay=True, dir_okay=False),
    labels: Path = typer.Option(..., "--labels", exists=True, file_okay=True, dir_okay=False),
    quarantine: Path = typer.Option(..., "--quarantine", exists=True, file_okay=True, dir_okay=False),
    output_markdown: Path = typer.Option(..., "--output-markdown"),
    output_json: Path | None = typer.Option(None, "--output-json"),
) -> None:
    data = build_portfolio(summary, labels, quarantine)
    write_portfolio_markdown(output_markdown, data)
    typer.echo(f"wrote {output_markdown}")
    if output_json:
        write_portfolio_json(output_json, data)
        typer.echo(f"wrote {output_json}")


@app.command("baseline-create")
def baseline_create(
    summary: Path = typer.Option(..., "--summary", exists=True, file_okay=True, dir_okay=False),
    labels: Path = typer.Option(..., "--labels", exists=True, file_okay=True, dir_okay=False),
    quarantine: Path = typer.Option(..., "--quarantine", exists=True, file_okay=True, dir_okay=False),
    output_baseline: Path = typer.Option(..., "--output-baseline"),
) -> None:
    create_baseline(summary, labels, quarantine, output_baseline)
    typer.echo(f"wrote {output_baseline}")


@app.command("drift-report")
def drift_report(
    baseline: Path = typer.Option(..., "--baseline", exists=True, file_okay=True, dir_okay=False),
    current_summary: Path = typer.Option(..., "--current-summary", exists=True, file_okay=True, dir_okay=False),
    current_labels: Path = typer.Option(..., "--current-labels", exists=True, file_okay=True, dir_okay=False),
    current_quarantine: Path = typer.Option(..., "--current-quarantine", exists=True, file_okay=True, dir_okay=False),
    output_json: Path = typer.Option(..., "--output-json"),
    output_markdown: Path | None = typer.Option(None, "--output-markdown"),
) -> None:
    report = compare_baseline(baseline, current_summary, current_labels, current_quarantine, output_json, output_markdown)
    typer.echo(f"wrote {output_json}")
    if output_markdown:
        typer.echo(f"wrote {output_markdown}")
    typer.echo(f"nodes_changed={report['counts']['nodes_changed']}")


@app.command("handoff-bundle")
def handoff_bundle(
    output_zip: Path = typer.Option(..., "--output-zip"),
    labels: Path = typer.Option(..., "--labels", exists=True, file_okay=True, dir_okay=False),
    quarantine: Path = typer.Option(..., "--quarantine", exists=True, file_okay=True, dir_okay=False),
    review_queue: Path | None = typer.Option(None, "--review-queue", exists=False, file_okay=True, dir_okay=False),
    slurm_fragment: Path = typer.Option(..., "--slurm-fragment", exists=True, file_okay=True, dir_okay=False),
    drain_review: Path = typer.Option(..., "--drain-review", exists=True, file_okay=True, dir_okay=False),
    summary: Path = typer.Option(..., "--summary", exists=True, file_okay=True, dir_okay=False),
    policy: Path | None = typer.Option(None, "--policy", exists=False, file_okay=True, dir_okay=False),
    evidence_bundle: Path | None = typer.Option(None, "--evidence-bundle", exists=False, file_okay=True, dir_okay=False),
    markdown_summary: Path | None = typer.Option(None, "--markdown-summary", exists=False, file_okay=True, dir_okay=False),
    schemas_dir: Path | None = typer.Option(Path("schemas"), "--schemas-dir", exists=False, file_okay=False, dir_okay=True),
    docs_dir: Path | None = typer.Option(Path("docs"), "--docs-dir", exists=False, file_okay=False, dir_okay=True),
    scripts_dir: Path | None = typer.Option(Path("scripts"), "--scripts-dir", exists=False, file_okay=False, dir_okay=True),
) -> None:
    files = {
        "labels/slurm_node_labels.csv": labels,
        "labels/quarantine.csv": quarantine,
        "labels/review_queue.csv": review_queue,
        "slurm/slurm_features.conf.snippet": slurm_fragment,
        "slurm/drain_review.sh": drain_review,
        "summary/summary.json": summary,
        "summary/qualification_summary.md": markdown_summary,
        "policy/qualification_policy.yml": policy,
        "evidence/evidence_bundle.json": evidence_bundle,
    }
    manifest = create_handoff_bundle(output_zip, files, include_dirs={"schemas": schemas_dir, "docs": docs_dir, "scripts": scripts_dir})
    typer.echo(f"wrote {output_zip}")
    typer.echo(f"files={len(manifest['files'])}")


@app.command("validate-schemas")
def validate_schemas(
    schemas_dir: Path = typer.Option(Path("schemas"), "--schemas-dir", exists=False, file_okay=False, dir_okay=True),
    policy: Path | None = typer.Option(None, "--policy", exists=False, file_okay=True, dir_okay=False),
    node_inventory: Path | None = typer.Option(None, "--node-inventory", exists=False, file_okay=True, dir_okay=False),
    summary: Path | None = typer.Option(None, "--summary", exists=False, file_okay=True, dir_okay=False),
    labels: Path | None = typer.Option(None, "--labels", exists=False, file_okay=True, dir_okay=False),
    quarantine: Path | None = typer.Option(None, "--quarantine", exists=False, file_okay=True, dir_okay=False),
    review_queue: Path | None = typer.Option(None, "--review-queue", exists=False, file_okay=True, dir_okay=False),
    evidence_bundle: Path | None = typer.Option(None, "--evidence-bundle", exists=False, file_okay=True, dir_okay=False),
    slurm_fragment: Path | None = typer.Option(None, "--slurm-fragment", exists=False, file_okay=True, dir_okay=False),
    drain_review: Path | None = typer.Option(None, "--drain-review", exists=False, file_okay=True, dir_okay=False),
) -> None:
    errors = validate_artifacts(
        schemas_dir=schemas_dir,
        policy=policy,
        inventory=node_inventory,
        summary=summary,
        labels=labels,
        quarantine=quarantine,
        review_queue=review_queue,
        evidence_bundle=evidence_bundle,
        slurm_fragment=slurm_fragment,
        drain_review=drain_review,
    )
    if errors:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(2)
    typer.echo("schema_validation=ok")


@app.command("runtime-guard")
def runtime_guard(
    src_dir: Path = typer.Option(Path("src/gpu_rack_qualifier"), "--src-dir", exists=False, file_okay=False, dir_okay=True),
) -> None:
    findings = run_runtime_guard(src_dir)
    if findings:
        for finding in findings:
            typer.echo(f"ERROR: {finding}", err=True)
        raise typer.Exit(2)
    typer.echo("runtime_guard=ok")


@app.command("coverage-report")
def coverage_report(
    evidence: Path = typer.Option(..., "--evidence", exists=False, file_okay=False, dir_okay=True),
    policy: Path | None = typer.Option(None, "--policy", exists=False, file_okay=True, dir_okay=False),
    node_inventory: Path | None = typer.Option(None, "--node-inventory", exists=False, file_okay=True, dir_okay=False),
    labels: Path | None = typer.Option(None, "--labels", exists=False, file_okay=True, dir_okay=False),
    quarantine: Path | None = typer.Option(None, "--quarantine", exists=False, file_okay=True, dir_okay=False),
    summary: Path | None = typer.Option(None, "--summary", exists=False, file_okay=True, dir_okay=False),
    output_json: Path = typer.Option(..., "--output-json"),
    output_markdown: Path | None = typer.Option(None, "--output-markdown"),
) -> None:
    qualification_policy = _load_policy_or_exit(policy, strict=True)
    inventory = _load_inventory_or_exit(node_inventory, strict=True)
    report = build_coverage_report(evidence, qualification_policy, inventory, labels, quarantine, summary)
    write_coverage_json(output_json, report)
    typer.echo(f"wrote {output_json}")
    if output_markdown:
        write_coverage_markdown(output_markdown, report)
        typer.echo(f"wrote {output_markdown}")
    typer.echo(f"nodes_seen={report['input']['nodes_seen']}")
    typer.echo(f"data_gaps={len(report['data_gaps'])}")


@app.command("simulate-policies")
def simulate_policies_command(
    evidence: Path = typer.Option(..., "--evidence", exists=False, file_okay=False, dir_okay=True),
    policy: list[Path] = typer.Option(..., "--policy", exists=False, file_okay=True, dir_okay=False),
    node_inventory: Path | None = typer.Option(None, "--node-inventory", exists=False, file_okay=True, dir_okay=False),
    output_json: Path = typer.Option(..., "--output-json"),
    output_csv: Path | None = typer.Option(None, "--output-csv"),
) -> None:
    inventory = _load_inventory_or_exit(node_inventory, strict=True)
    report = simulate_policies(evidence, policy, inventory)
    write_simulation_json(output_json, report)
    typer.echo(f"wrote {output_json}")
    if output_csv:
        write_simulation_csv(output_csv, report)
        typer.echo(f"wrote {output_csv}")
    typer.echo(f"policies={len(report['simulations'])}")


@app.command("impact-report")
def impact_report(
    summary: Path = typer.Option(..., "--summary", exists=True, file_okay=True, dir_okay=False),
    labels: Path = typer.Option(..., "--labels", exists=True, file_okay=True, dir_okay=False),
    quarantine: Path = typer.Option(..., "--quarantine", exists=True, file_okay=True, dir_okay=False),
    output_json: Path = typer.Option(..., "--output-json"),
    output_markdown: Path | None = typer.Option(None, "--output-markdown"),
    gpus_per_node: int | None = typer.Option(None, "--gpus-per-node"),
    hours_at_risk: float | None = typer.Option(None, "--hours-at-risk"),
    accelerator_hour_value: float | None = typer.Option(None, "--accelerator-hour-value"),
) -> None:
    report = build_business_impact_report(summary, labels, quarantine, gpus_per_node, hours_at_risk, accelerator_hour_value)
    write_business_impact_json(output_json, report)
    typer.echo(f"wrote {output_json}")
    if output_markdown:
        write_business_impact_markdown(output_markdown, report)
        typer.echo(f"wrote {output_markdown}")


def _load_policy_or_exit(policy: Path | None, strict: bool):
    try:
        return load_policy(policy)
    except Exception as exc:
        if strict:
            typer.echo(f"ERROR: policy YAML is invalid: {exc}", err=True)
            raise typer.Exit(2) from exc
        typer.echo(f"WARNING: policy YAML is invalid, using defaults: {exc}", err=True)
        return load_policy(None)


def _load_inventory_or_exit(path: Path | None, strict: bool):
    try:
        return load_node_inventory(path)
    except Exception as exc:
        if strict:
            typer.echo(f"ERROR: node inventory YAML is invalid: {exc}", err=True)
            raise typer.Exit(2) from exc
        typer.echo(f"WARNING: node inventory YAML is invalid, continuing without inventory: {exc}", err=True)
        return None


def _require_paths(paths: dict[str, Path | None]) -> None:
    missing = [name for name, value in paths.items() if value is None]
    if missing:
        typer.echo(f"ERROR: missing required option(s): {', '.join('--' + item for item in missing)}", err=True)
        raise typer.Exit(2)


def _validate_inputs(evidence_dir: Path, nodes, policy, inventory, strict: bool) -> None:
    errors: list[str] = []
    if not evidence_dir.exists():
        errors.append(f"evidence directory missing: {evidence_dir}")
    if not nodes:
        errors.append("no evidence node folders found")
    if policy.evidence.require_node_inventory and inventory is None:
        errors.append("node inventory is required by policy but absent")
    if strict:
        for node in nodes:
            if policy.evidence.require_nccl_single_node and not node.nccl_single.present:
                errors.append(f"{node.node_name}: missing nccl_single_node_all_reduce.txt")
            if policy.evidence.require_topo and not node.topology.present:
                errors.append(f"{node.node_name}: missing nvidia_smi_topo_m.txt")
            if policy.evidence.require_nvidia_smi_query and not node.nvidia_smi_query.present:
                errors.append(f"{node.node_name}: missing nvidia_smi_query.xml")
            if policy.evidence.require_bmc_snapshot and not node.bmc_snapshot.present:
                errors.append(f"{node.node_name}: missing bmc_sensors.redfish.json")
        if nodes and policy.evidence.require_nccl_single_node and not any(node.nccl_single.parsed for node in nodes):
            errors.append("NCCL output is malformed for all nodes")
    if errors and strict:
        for error in errors:
            typer.echo(f"ERROR: {error}", err=True)
        raise typer.Exit(2)
    if errors and not strict:
        for error in errors:
            typer.echo(f"WARNING: {error}", err=True)


def _non_strict_warnings(nodes, policy) -> list[str]:
    warnings: list[str] = []
    for node in nodes:
        if policy.evidence.require_nccl_single_node and not node.nccl_single.present:
            warnings.append(f"{node.node_name}: NCCL single-node evidence missing; node will require review")
        if policy.evidence.require_topo and not node.topology.present:
            warnings.append(f"{node.node_name}: topology evidence missing; node will require review")
        if policy.evidence.require_nvidia_smi_query and not node.nvidia_smi_query.present:
            warnings.append(f"{node.node_name}: nvidia-smi query evidence missing; node will require review")
        if policy.evidence.require_bmc_snapshot and not node.bmc_snapshot.present:
            warnings.append(f"{node.node_name}: BMC snapshot evidence missing; node will require review")
    return sorted(set(warnings))


if __name__ == "__main__":
    app()
