from __future__ import annotations

import csv
import json

import yaml
from typer.testing import CliRunner

from inference_placement_bench.bundles import BUNDLE_TEMPLATES, bundle_paths, init_bundle, validate_bundle
from inference_placement_bench.cli import app
from inference_placement_bench.prompt_packs import generate_prompt_rows


def test_init_bundle_generates_required_input_data(tmp_path):
    root = tmp_path / "bundle"
    init_bundle(root, template="low-latency-chat", prompt_count=12, seed=12345)
    paths = bundle_paths(root)
    required = [
        "workload",
        "endpoints",
        "constraints",
        "thresholds",
        "prompts",
        "rate_cards",
        "data_inventory",
        "request_streaming",
        "request_non_streaming",
        "runbook",
    ]
    assert all(paths[key].exists() for key in required)
    assert len(paths["prompts"].read_text(encoding="utf-8").splitlines()) == 12


def test_validate_bundle_accepts_generated_bundle(tmp_path):
    root = tmp_path / "bundle"
    init_bundle(root, template="cost-sensitive-embedding", prompt_count=50)
    errors, warnings = validate_bundle(root)
    assert errors == []
    assert warnings == []


def test_all_bundle_templates_generate_valid_input_data(tmp_path):
    for template, cfg in sorted(BUNDLE_TEMPLATES.items()):
        root = tmp_path / template
        init_bundle(root, template=template, prompt_count=cfg["measured_requests"])
        errors, warnings = validate_bundle(root)
        assert errors == []
        assert warnings == []


def test_generate_prompts_and_constraints_commands(tmp_path):
    runner = CliRunner()
    bundle = tmp_path / "bundle"
    init_result = runner.invoke(app, ["init-bundle", "--template", "customer-chat", "--output", str(bundle), "--prompt-count", "8"])
    assert init_result.exit_code == 0
    prompts = tmp_path / "prompts.jsonl"
    prompt_result = runner.invoke(
        app,
        [
            "generate-prompts",
            "--workload",
            str(bundle / "workload.yml"),
            "--output",
            str(prompts),
            "--count",
            "6",
        ],
    )
    assert prompt_result.exit_code == 0
    assert len(prompts.read_text(encoding="utf-8").splitlines()) == 6
    constraints = tmp_path / "constraints.yml"
    constraints_result = runner.invoke(
        app,
        ["generate-constraints", "--policy-pack", "regional-low-latency", "--output", str(constraints)],
    )
    assert constraints_result.exit_code == 0
    assert "latency_targets" in constraints.read_text(encoding="utf-8")


def test_prompt_pack_business_metadata_is_generated():
    rows = generate_prompt_rows("agent-tool-summary", count=3, seed=12345)
    assert rows[0]["metadata"]["business_task"] == "agent-tool-result-summary"
    assert rows[0]["metadata"]["business_impact"] == "operator-workflow-latency-screening"
    assert rows[0]["metadata"]["data_sensitivity"] == "none"
    assert rows[0]["synthetic"] is True


def test_bundle_cli_workflow_runs_offline_with_simulator(tmp_path):
    runner = CliRunner()
    bundle = tmp_path / "bundle"
    assert runner.invoke(app, ["init-bundle", "--template", "low-latency-chat", "--output", str(bundle), "--prompt-count", "10"]).exit_code == 0
    assert runner.invoke(app, ["validate-bundle", "--input", str(bundle)]).exit_code == 0

    simulated = tmp_path / "fake_endpoints.yml"
    simulate_result = runner.invoke(app, ["simulate", "--bundle", str(bundle), "--output", str(simulated)])
    assert simulate_result.exit_code == 0
    assert "simulator:" in simulated.read_text(encoding="utf-8")

    out = tmp_path / "out"
    plan_path = out / "plan.yml"
    plan_result = runner.invoke(
        app,
        ["plan", "--bundle", str(bundle), "--output-plan", str(plan_path), "--max-requests", "3", "--warmup-requests", "1"],
    )
    assert plan_result.exit_code == 0

    results_path = out / "results.json"
    samples_path = out / "samples.csv"
    run_result = runner.invoke(
        app,
        [
            "run",
            "--plan",
            str(plan_path),
            "--output-results",
            str(results_path),
            "--output-samples",
            str(samples_path),
            "--no-network",
            "--now",
            "2026-01-01T00:00:00Z",
        ],
    )
    assert run_result.exit_code == 0
    results = json.loads(results_path.read_text(encoding="utf-8"))
    assert results["endpoints"][0]["metrics"]["success_count"] == 3
    with samples_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    measured_rows = [row for row in rows if row["measured"] == "True"]
    assert len(measured_rows) == 9

    decision_bundle = out / "decision_bundle"
    recommend_result = runner.invoke(
        app,
        [
            "recommend",
            "--results",
            str(results_path),
            "--bundle",
            str(bundle),
            "--output-bundle",
            str(decision_bundle),
        ],
    )
    assert recommend_result.exit_code == 0
    assert (decision_bundle / "recommendation.json").exists()
    assert (decision_bundle / "recommendation.md").exists()
    assert (decision_bundle / "executive_summary.md").exists()
    assert (decision_bundle / "input_hashes.json").exists()
    assert (decision_bundle / "bundle_manifest.json").exists()
    manifest = json.loads((decision_bundle / "bundle_manifest.json").read_text(encoding="utf-8"))
    assert manifest["includes_executive_summary"] is True


def test_bundle_rate_cards_are_authoritative_for_plan_and_results(tmp_path):
    runner = CliRunner()
    bundle = tmp_path / "bundle"
    assert runner.invoke(app, ["init-bundle", "--template", "low-latency-chat", "--output", str(bundle), "--prompt-count", "6"]).exit_code == 0
    rate_cards = {
        "currency": "CAD",
        "rate_cards": [
            {"endpoint_id": "candidate_fast", "input_per_1m_tokens": 0.01, "output_per_1m_tokens": 0.02, "per_1k_requests": 0.0},
            {"endpoint_id": "candidate_balanced", "input_per_1m_tokens": 1.10, "output_per_1m_tokens": 3.80, "per_1k_requests": 0.0},
            {"endpoint_id": "candidate_low_cost", "input_per_1m_tokens": 10.0, "output_per_1m_tokens": 20.0, "per_1k_requests": 0.0},
        ],
    }
    (bundle / "rate_cards.yml").write_text(yaml.safe_dump(rate_cards, sort_keys=False), encoding="utf-8")

    out = tmp_path / "out"
    plan_path = out / "plan.yml"
    plan_result = runner.invoke(
        app,
        ["plan", "--bundle", str(bundle), "--output-plan", str(plan_path), "--max-requests", "1", "--warmup-requests", "0"],
    )
    assert plan_result.exit_code == 0
    plan_payload = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    economics_by_endpoint = {
        endpoint["endpoint_id"]: endpoint["unit_economics"] for endpoint in plan_payload["endpoint_profiles"]
    }
    assert economics_by_endpoint["candidate_fast"]["input_per_1m_tokens"] == 0.01
    assert economics_by_endpoint["candidate_low_cost"]["input_per_1m_tokens"] == 10.0

    results_path = out / "results.json"
    samples_path = out / "samples.csv"
    run_result = runner.invoke(
        app,
        [
            "run",
            "--plan",
            str(plan_path),
            "--output-results",
            str(results_path),
            "--output-samples",
            str(samples_path),
            "--no-network",
            "--now",
            "2026-01-01T00:00:00Z",
        ],
    )
    assert run_result.exit_code == 0
    results = json.loads(results_path.read_text(encoding="utf-8"))
    cost_by_endpoint = {
        endpoint["endpoint_id"]: endpoint["economics"]["estimated_cost_per_1k_requests"]
        for endpoint in results["endpoints"]
    }
    assert cost_by_endpoint["candidate_fast"] < cost_by_endpoint["candidate_low_cost"]


def test_evaluate_command_creates_complete_decision_bundle(tmp_path):
    runner = CliRunner()
    bundle = tmp_path / "bundle"
    assert runner.invoke(app, ["init-bundle", "--template", "low-latency-chat", "--output", str(bundle), "--prompt-count", "8"]).exit_code == 0

    output_bundle = tmp_path / "decision"
    result = runner.invoke(
        app,
        [
            "evaluate",
            "--bundle",
            str(bundle),
            "--output-bundle",
            str(output_bundle),
            "--max-requests",
            "2",
            "--warmup-requests",
            "0",
            "--no-network",
            "--now",
            "2026-01-01T00:00:00Z",
        ],
    )
    assert result.exit_code == 0
    assert (output_bundle / "run_artifacts" / "benchmark_plan.yml").exists()
    assert (output_bundle / "run_artifacts" / "results.json").exists()
    assert (output_bundle / "run_artifacts" / "samples.csv").exists()
    assert (output_bundle / "recommendation.json").exists()
    assert (output_bundle / "recommendation.md").exists()
    assert (output_bundle / "executive_summary.md").exists()
    assert (output_bundle / "results.json").exists()


def test_negative_bundle_templates_cover_policy_and_no_passing_cases(tmp_path):
    runner = CliRunner()
    blocked = tmp_path / "blocked"
    assert runner.invoke(app, ["init-bundle", "--template", "location-blocked-fastest", "--output", str(blocked), "--prompt-count", "6"]).exit_code == 0
    blocked_plan = tmp_path / "blocked_plan.yml"
    blocked_result = runner.invoke(
        app,
        ["plan", "--bundle", str(blocked), "--output-plan", str(blocked_plan), "--max-requests", "1", "--warmup-requests", "0"],
    )
    assert blocked_result.exit_code == 0
    blocked_payload = yaml.safe_load(blocked_plan.read_text(encoding="utf-8"))
    fast = next(endpoint for endpoint in blocked_payload["endpoints"] if endpoint["endpoint_id"] == "candidate_fast")
    assert fast["eligible"] is False
    assert "DECLARED_LOCATION_NOT_ALLOWED" in fast["eligibility_reason_codes"]

    no_passing = tmp_path / "no_passing"
    assert runner.invoke(app, ["init-bundle", "--template", "no-passing-endpoints", "--output", str(no_passing), "--prompt-count", "6"]).exit_code == 0
    decision = tmp_path / "no_passing_decision"
    no_passing_result = runner.invoke(
        app,
        [
            "evaluate",
            "--bundle",
            str(no_passing),
            "--output-bundle",
            str(decision),
            "--max-requests",
            "1",
            "--warmup-requests",
            "0",
            "--no-network",
            "--now",
            "2026-01-01T00:00:00Z",
        ],
    )
    assert no_passing_result.exit_code == 0
    recommendation = json.loads((decision / "recommendation.json").read_text(encoding="utf-8"))
    assert recommendation["recommendation_status"] == "NO_ENDPOINT_MEETS_CONSTRAINTS"
