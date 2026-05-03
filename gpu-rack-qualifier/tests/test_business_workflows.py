import csv
import json
import os
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from gpu_rack_qualifier.cli import app


runner = CliRunner()


def test_generate_fixtures_creates_complete_input_data_and_expected_outputs(tmp_path):
    output_dir = tmp_path / "generated"
    result = runner.invoke(
        app,
        [
            "generate-fixtures",
            "--output-dir",
            str(output_dir),
            "--nodes",
            "20",
            "--gpus-per-node",
            "4",
            "--scenario",
            "mixed_commissioning",
            "--seed",
            "3",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (output_dir / "qualification_policy.yml").exists()
    assert (output_dir / "node_inventory.yml").exists()
    assert (output_dir / "scenario_manifest.csv").exists()
    assert (output_dir / "evidence" / "node001" / "nccl_single_node_all_reduce.txt").exists()
    assert (output_dir / "evidence" / "node001" / "nvidia_smi_query.xml").exists()
    assert (output_dir / "evidence" / "node001" / "collection_metadata.json").exists()
    assert "power_readings" in (output_dir / "evidence" / "node001" / "nvidia_smi_query.xml").read_text(encoding="utf-8")
    assert "Power Supply Redundancy" in (output_dir / "evidence" / "node001" / "bmc_sensors.redfish.json").read_text(encoding="utf-8")
    assert (output_dir / "expected" / "slurm_node_labels.csv").exists()
    assert (output_dir / "expected" / "review_queue.csv").exists()
    assert (output_dir / "expected" / "evidence_bundle.json").exists()
    assert not (output_dir / "evidence" / "node015" / "nvidia_smi_topo_m.txt").exists()
    assert (output_dir / "evidence" / "node016" / "nccl_single_node_all_reduce.txt").read_text(encoding="utf-8").startswith("this is not parseable")
    assert (output_dir / "evidence" / "node017" / "nvidia_smi_query.xml").read_text(encoding="utf-8").startswith("<nvidia_smi_log><gpu>")
    bundle = json.loads((output_dir / "expected" / "evidence_bundle.json").read_text(encoding="utf-8"))
    assert bundle["schema_version"] == "rackq.evidence_bundle.v1"
    with (output_dir / "scenario_manifest.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["expected_business_impact"]


def test_all_fixture_scenarios_generate_and_qualify(tmp_path):
    scenarios = [
        "pass",
        "missing_pairwise_nccl",
        "weak_pairwise",
        "topology_weak_path",
        "topology_review_path",
        "sensor_warning",
        "correctness_error",
        "wrong_count",
        "timeout",
        "missing_gpu",
        "vbios_mismatch",
        "cuda_drift",
        "ecc_mismatch",
        "mig_mismatch",
        "missing_topology",
        "malformed_nccl",
        "malformed_xml",
        "rack_wide_slow_baseline",
        "partial_evidence",
        "bmc_critical",
        "temperature_warning",
        "temperature_critical",
        "sensor_critical",
        "fan_failure",
        "driver_drift",
    ]
    for scenario in scenarios:
        output_dir = tmp_path / scenario
        generated = runner.invoke(app, ["generate-fixtures", "--output-dir", str(output_dir), "--nodes", "3", "--gpus-per-node", "4", "--scenario", scenario])
        assert generated.exit_code == 0, generated.output
        run_dir = output_dir / "run"
        qualified = runner.invoke(
            app,
            [
                "qualify",
                "--evidence",
                str(output_dir / "evidence"),
                "--node-inventory",
                str(output_dir / "node_inventory.yml"),
                "--policy",
                str(output_dir / "qualification_policy.yml"),
                "--output-labels",
                str(run_dir / "labels.csv"),
                "--output-quarantine",
                str(run_dir / "quarantine.csv"),
                "--output-slurm-fragment",
                str(run_dir / "features.conf"),
                "--output-drain-review",
                str(run_dir / "drain_review.sh"),
                "--summary",
                str(run_dir / "summary.json"),
                "--evidence-bundle",
                str(run_dir / "evidence_bundle.json"),
            ],
        )
        assert qualified.exit_code == 0, qualified.output
        assert (run_dir / "summary.json").exists()


def test_schema_artifacts_are_valid_json():
    schema_names = [
        "qualification_policy.schema.json",
        "node_inventory.schema.json",
        "evidence_bundle.schema.json",
        "summary.schema.json",
        "labels.schema.json",
        "quarantine.schema.json",
        "review_queue.schema.json",
    ]
    for name in schema_names:
        data = json.loads((Path("schemas") / name).read_text(encoding="utf-8"))
        assert data["$schema"].startswith("https://json-schema.org/")
        assert data["title"].startswith("gpu-rack-qualifier")


def test_validate_schemas_command_accepts_generated_outputs(tmp_path):
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "qualify",
            "--evidence",
            "examples/evidence",
            "--node-inventory",
            "examples/node_inventory.yml",
            "--policy",
            "examples/qualification_policy.yml",
            "--output-labels",
            str(out / "labels.csv"),
            "--output-quarantine",
            str(out / "quarantine.csv"),
            "--output-slurm-fragment",
            str(out / "features.conf"),
            "--output-drain-review",
            str(out / "drain_review.sh"),
            "--summary",
            str(out / "summary.json"),
            "--evidence-bundle",
            str(out / "evidence_bundle.json"),
        ],
    )
    assert result.exit_code == 0, result.output
    validated = runner.invoke(
        app,
        [
            "validate-schemas",
            "--schemas-dir",
            "schemas",
            "--policy",
            "examples/qualification_policy.yml",
            "--node-inventory",
            "examples/node_inventory.yml",
            "--summary",
            str(out / "summary.json"),
            "--labels",
            str(out / "labels.csv"),
            "--quarantine",
            str(out / "quarantine.csv"),
            "--review-queue",
            str(out / "review_queue.csv"),
            "--evidence-bundle",
            str(out / "evidence_bundle.json"),
            "--slurm-fragment",
            str(out / "features.conf"),
            "--drain-review",
            str(out / "drain_review.sh"),
        ],
    )
    assert validated.exit_code == 0, validated.output
    assert "schema_validation=ok" in validated.output


def test_validate_evidence_accepts_inventory_and_schemas():
    result = runner.invoke(
        app,
        [
            "validate-evidence",
            "--evidence",
            "examples/evidence",
            "--policy",
            "examples/qualification_policy.yml",
            "--node-inventory",
            "examples/node_inventory.yml",
            "--schemas-dir",
            "schemas",
            "--strict",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "nodes_seen=4" in result.output


def test_qualify_writes_evidence_bundle_and_business_metrics(tmp_path):
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "qualify",
            "--evidence",
            "examples/evidence",
            "--node-inventory",
            "examples/node_inventory.yml",
            "--policy",
            "examples/qualification_policy.yml",
            "--output-labels",
            str(out / "labels.csv"),
            "--output-quarantine",
            str(out / "quarantine.csv"),
            "--output-slurm-fragment",
            str(out / "features.conf"),
            "--output-drain-review",
            str(out / "drain_review.sh"),
            "--summary",
            str(out / "summary.json"),
            "--evidence-bundle",
            str(out / "evidence_bundle.json"),
        ],
    )
    assert result.exit_code == 0, result.output
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["business_impact"]["nodes_without_multinode_label"] == 2
    assert summary["business_impact"]["action_queue_nodes"] == summary["action_queue_counts"]["total"]
    assert summary["readiness"]["AVOID_MULTINODE"] == 1
    bundle = json.loads((out / "evidence_bundle.json").read_text(encoding="utf-8"))
    assert bundle["mode"] == "REVIEW_ONLY"
    assert bundle["nodes"][0]["policy_decisions"]
    assert bundle["business_impact"]["nodes_without_multinode_label"] == summary["business_impact"]["nodes_without_multinode_label"]


def test_redacted_evidence_bundle_hides_node_and_rack_names(tmp_path):
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "qualify",
            "--evidence",
            "examples/evidence",
            "--node-inventory",
            "examples/node_inventory.yml",
            "--policy",
            "examples/qualification_policy.yml",
            "--output-labels",
            str(out / "labels.csv"),
            "--output-quarantine",
            str(out / "quarantine.csv"),
            "--output-slurm-fragment",
            str(out / "features.conf"),
            "--output-drain-review",
            str(out / "drain_review.sh"),
            "--summary",
            str(out / "summary.json"),
            "--evidence-bundle",
            str(out / "evidence_bundle.json"),
            "--redact",
        ],
    )
    assert result.exit_code == 0, result.output
    text = (out / "evidence_bundle.json").read_text(encoding="utf-8")
    assert "gpu001" not in text
    assert "rack-a01" not in text
    assert "node_001" in text
    bundle = json.loads(text)
    assert bundle["redacted"] is True
    assert bundle["nodes"][0]["files"][0]["sha256"] == "REDACTED"
    assert bundle["nodes"][0]["files"][0]["bytes"] is None
    assert bundle["nodes"][0]["files"][0]["fingerprint_redacted"] is True


def test_pairwise_plan_and_sbatch_template_are_review_only(tmp_path):
    plan = tmp_path / "pairwise_plan.csv"
    result = runner.invoke(app, ["generate-pairwise-plan", "--node-list", "node003,node001,node002", "--output-csv", str(plan), "--strategy", "ring", "--gpus-per-node", "4"])
    assert result.exit_code == 0, result.output
    with plan.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["nodes"] == "node001|node002"
    script = tmp_path / "pairwise_template.sh"
    result = runner.invoke(app, ["generate-sbatch-template", "--plan-csv", str(plan), "--output-script", str(script), "--nccl-all-reduce", "/path/all_reduce_perf", "--gpus-per-node", "4"])
    assert result.exit_code == 0, result.output
    text = script.read_text(encoding="utf-8")
    assert "not submitted" in text
    active_lines = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
    assert not any(line.startswith("sbatch ") for line in active_lines)
    assert not (script.stat().st_mode & os.X_OK)


def test_pairwise_plan_supports_switch_and_fabric_groups(tmp_path):
    generated = tmp_path / "generated"
    result = runner.invoke(app, ["generate-fixtures", "--output-dir", str(generated), "--nodes", "18", "--gpus-per-node", "4", "--scenario", "pass"])
    assert result.exit_code == 0, result.output
    same_switch = tmp_path / "same_switch.csv"
    cross_fabric = tmp_path / "cross_fabric.csv"
    result = runner.invoke(app, ["generate-pairwise-plan", "--node-inventory", str(generated / "node_inventory.yml"), "--output-csv", str(same_switch), "--strategy", "same-switch"])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["generate-pairwise-plan", "--node-inventory", str(generated / "node_inventory.yml"), "--output-csv", str(cross_fabric), "--strategy", "cross-fabric"])
    assert result.exit_code == 0, result.output
    with same_switch.open(encoding="utf-8", newline="") as handle:
        same_rows = list(csv.DictReader(handle))
    with cross_fabric.open(encoding="utf-8", newline="") as handle:
        cross_rows = list(csv.DictReader(handle))
    assert same_rows and all(row["fabric"] == "same-switch" for row in same_rows)
    assert cross_rows and all(row["fabric"] == "cross-fabric" for row in cross_rows)


def test_import_helpers_portfolio_baseline_drift_and_handoff(tmp_path):
    out = tmp_path / "out"
    qualify = runner.invoke(
        app,
        [
            "qualify",
            "--evidence",
            "examples/evidence",
            "--node-inventory",
            "examples/node_inventory.yml",
            "--policy",
            "examples/qualification_policy.yml",
            "--output-labels",
            str(out / "labels.csv"),
            "--output-quarantine",
            str(out / "quarantine.csv"),
            "--output-slurm-fragment",
            str(out / "features.conf"),
            "--output-drain-review",
            str(out / "drain_review.sh"),
            "--summary",
            str(out / "summary.json"),
            "--evidence-bundle",
            str(out / "evidence_bundle.json"),
        ],
    )
    assert qualify.exit_code == 0, qualify.output
    bmc = runner.invoke(app, ["import-bmc-snapshot", "--input-json", "examples/evidence/gpu001/bmc_sensors.redfish.json", "--output-json", str(out / "bmc.normalized.json")])
    assert bmc.exit_code == 0, bmc.output
    normalized = json.loads((out / "bmc.normalized.json").read_text(encoding="utf-8"))
    assert normalized["schema_version"] == "rackq.normalized_bmc_snapshot.v1"
    inventory_csv = out / "inventory.csv"
    inventory_csv.write_text("name,rack,expected_gpu_count,expected_nic_count,expected_role,expected_features\nnode001,rack-a,4,2,training|inference,gpu|training\n", encoding="utf-8")
    imported = runner.invoke(app, ["import-inventory-csv", "--input-csv", str(inventory_csv), "--output-yml", str(out / "inventory.yml"), "--cluster-id", "cluster-a", "--rack-id", "rack-a"])
    assert imported.exit_code == 0, imported.output
    portfolio = runner.invoke(app, ["portfolio", "--summary", str(out / "summary.json"), "--labels", str(out / "labels.csv"), "--quarantine", str(out / "quarantine.csv"), "--output-markdown", str(out / "portfolio.md"), "--output-json", str(out / "portfolio.json")])
    assert portfolio.exit_code == 0, portfolio.output
    baseline = runner.invoke(app, ["baseline-create", "--summary", str(out / "summary.json"), "--labels", str(out / "labels.csv"), "--quarantine", str(out / "quarantine.csv"), "--output-baseline", str(out / "baseline.json")])
    assert baseline.exit_code == 0, baseline.output
    drift = runner.invoke(app, ["drift-report", "--baseline", str(out / "baseline.json"), "--current-summary", str(out / "summary.json"), "--current-labels", str(out / "labels.csv"), "--current-quarantine", str(out / "quarantine.csv"), "--output-json", str(out / "drift.json"), "--output-markdown", str(out / "drift.md")])
    assert drift.exit_code == 0, drift.output
    handoff = runner.invoke(
        app,
        [
            "handoff-bundle",
            "--output-zip",
            str(out / "handoff.zip"),
            "--labels",
            str(out / "labels.csv"),
            "--quarantine",
            str(out / "quarantine.csv"),
            "--review-queue",
            str(out / "review_queue.csv"),
            "--slurm-fragment",
            str(out / "features.conf"),
            "--drain-review",
            str(out / "drain_review.sh"),
            "--summary",
            str(out / "summary.json"),
            "--policy",
            "examples/qualification_policy.yml",
            "--evidence-bundle",
            str(out / "evidence_bundle.json"),
            "--markdown-summary",
            str(out / "portfolio.md"),
        ],
    )
    assert handoff.exit_code == 0, handoff.output
    with zipfile.ZipFile(out / "handoff.zip") as archive:
        names = set(archive.namelist())
        assert "manifest.json" in names
        assert "labels/slurm_node_labels.csv" in names
        assert "labels/review_queue.csv" in names
        assert "schemas/evidence_bundle.schema.json" in names
        assert "docs/operator_playbook.md" in names
        assert "scripts/check.sh" in names


def test_coverage_report_evaluates_input_and_output_coverage(tmp_path):
    generated = tmp_path / "generated"
    run = generated / "run"
    result = runner.invoke(app, ["generate-fixtures", "--output-dir", str(generated), "--nodes", "25", "--gpus-per-node", "4", "--scenario", "mixed_commissioning"])
    assert result.exit_code == 0, result.output
    qualified = runner.invoke(
        app,
        [
            "qualify",
            "--evidence",
            str(generated / "evidence"),
            "--node-inventory",
            str(generated / "node_inventory.yml"),
            "--policy",
            str(generated / "qualification_policy.yml"),
            "--output-labels",
            str(run / "labels.csv"),
            "--output-quarantine",
            str(run / "quarantine.csv"),
            "--output-slurm-fragment",
            str(run / "features.conf"),
            "--output-drain-review",
            str(run / "drain_review.sh"),
            "--summary",
            str(run / "summary.json"),
        ],
    )
    assert qualified.exit_code == 0, qualified.output
    coverage = runner.invoke(
        app,
        [
            "coverage-report",
            "--evidence",
            str(generated / "evidence"),
            "--node-inventory",
            str(generated / "node_inventory.yml"),
            "--policy",
            str(generated / "qualification_policy.yml"),
            "--labels",
            str(run / "labels.csv"),
            "--quarantine",
            str(run / "quarantine.csv"),
            "--summary",
            str(run / "summary.json"),
            "--output-json",
            str(run / "coverage.json"),
            "--output-markdown",
            str(run / "coverage.md"),
        ],
    )
    assert coverage.exit_code == 0, coverage.output
    report = json.loads((run / "coverage.json").read_text(encoding="utf-8"))
    assert report["schema_version"] == "rackq.coverage_report.v1"
    assert report["input"]["nodes_seen"] == 25
    assert report["signal_coverage"]["weak_pairwise_nodes"] > 0
    assert report["file_coverage_pct"]["collection_metadata_json"] == 100.0
    assert report["signal_coverage"]["malformed_nccl_nodes"] > 0
    assert report["output_coverage"]["business_impact_present"] is True


def test_policy_simulation_and_impact_report(tmp_path):
    generated = tmp_path / "generated"
    run = generated / "run"
    result = runner.invoke(app, ["generate-fixtures", "--output-dir", str(generated), "--nodes", "12", "--gpus-per-node", "4", "--scenario", "mixed_commissioning"])
    assert result.exit_code == 0, result.output
    strict_policy = tmp_path / "strict_policy.yml"
    strict_policy.write_text((generated / "qualification_policy.yml").read_text(encoding="utf-8").replace("policy_id: generated-default", "policy_id: strict-sim").replace("min_pairwise_busbw_gbps: 250", "min_pairwise_busbw_gbps: 380"), encoding="utf-8")
    simulation = runner.invoke(
        app,
        [
            "simulate-policies",
            "--evidence",
            str(generated / "evidence"),
            "--node-inventory",
            str(generated / "node_inventory.yml"),
            "--policy",
            str(generated / "qualification_policy.yml"),
            "--policy",
            str(strict_policy),
            "--output-json",
            str(run / "simulation.json"),
            "--output-csv",
            str(run / "simulation.csv"),
        ],
    )
    assert simulation.exit_code == 0, simulation.output
    simulation_report = json.loads((run / "simulation.json").read_text(encoding="utf-8"))
    assert simulation_report["schema_version"] == "rackq.policy_simulation.v1"
    assert len(simulation_report["simulations"]) == 2
    assert simulation_report["deltas"]
    qualified = runner.invoke(
        app,
        [
            "qualify",
            "--evidence",
            str(generated / "evidence"),
            "--node-inventory",
            str(generated / "node_inventory.yml"),
            "--policy",
            str(generated / "qualification_policy.yml"),
            "--output-labels",
            str(run / "labels.csv"),
            "--output-quarantine",
            str(run / "quarantine.csv"),
            "--output-slurm-fragment",
            str(run / "features.conf"),
            "--output-drain-review",
            str(run / "drain_review.sh"),
            "--summary",
            str(run / "summary.json"),
        ],
    )
    assert qualified.exit_code == 0, qualified.output
    impact = runner.invoke(
        app,
        [
            "impact-report",
            "--summary",
            str(run / "summary.json"),
            "--labels",
            str(run / "labels.csv"),
            "--quarantine",
            str(run / "quarantine.csv"),
            "--output-json",
            str(run / "impact.json"),
            "--output-markdown",
            str(run / "impact.md"),
            "--gpus-per-node",
            "4",
            "--hours-at-risk",
            "12",
            "--accelerator-hour-value",
            "2.5",
        ],
    )
    assert impact.exit_code == 0, impact.output
    impact_report = json.loads((run / "impact.json").read_text(encoding="utf-8"))
    assert impact_report["schema_version"] == "rackq.business_impact.v1"
    assert impact_report["operator_supplied_estimated_value_at_risk"] is not None


def test_runbook_qualify_and_demo_command_create_complete_story_outputs(tmp_path):
    runbook = tmp_path / "runbook.yml"
    output_dir = tmp_path / "runbook_out"
    runbook.write_text(
        "\n".join(
            [
                f"evidence: {Path('examples/evidence').resolve()}",
                f"node_inventory: {Path('examples/node_inventory.yml').resolve()}",
                f"policy: {Path('examples/qualification_policy.yml').resolve()}",
                f"business_assumptions: {Path('examples/business_assumptions.yml').resolve()}",
                "outputs:",
                f"  dir: {output_dir}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    qualified = runner.invoke(app, ["qualify", "--runbook", str(runbook)])
    assert qualified.exit_code == 0, qualified.output
    assert (output_dir / "review_queue.csv").exists()
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["business_impact"]["operator_supplied_estimated_value_at_risk"] is not None

    demo_dir = tmp_path / "demo"
    demo = runner.invoke(app, ["demo", "--output-dir", str(demo_dir), "--nodes", "8", "--gpus-per-node", "4", "--force"])
    assert demo.exit_code == 0, demo.output
    for name in [
        "slurm_node_labels.csv",
        "quarantine.csv",
        "review_queue.csv",
        "qualification_summary.md",
        "rack_portfolio.md",
        "coverage.json",
        "business_impact.json",
        "rackq_handoff.zip",
    ]:
        assert (demo_dir / "run" / name).exists()
    assert (demo_dir / "scenario_manifest.csv").exists()


def test_runtime_guard_command_passes_core_source():
    result = runner.invoke(app, ["runtime-guard", "--src-dir", "src/gpu_rack_qualifier"])
    assert result.exit_code == 0, result.output
    assert "runtime_guard=ok" in result.output


def test_malformed_xml_is_prominent_primary_reason(tmp_path):
    generated = tmp_path / "generated"
    run = generated / "run"
    result = runner.invoke(app, ["generate-fixtures", "--output-dir", str(generated), "--nodes", "2", "--gpus-per-node", "4", "--scenario", "malformed_xml"])
    assert result.exit_code == 0, result.output
    qualified = runner.invoke(
        app,
        [
            "qualify",
            "--evidence",
            str(generated / "evidence"),
            "--node-inventory",
            str(generated / "node_inventory.yml"),
            "--policy",
            str(generated / "qualification_policy.yml"),
            "--output-labels",
            str(run / "labels.csv"),
            "--output-quarantine",
            str(run / "quarantine.csv"),
            "--output-slurm-fragment",
            str(run / "features.conf"),
            "--output-drain-review",
            str(run / "drain_review.sh"),
            "--summary",
            str(run / "summary.json"),
        ],
    )
    assert qualified.exit_code == 0, qualified.output
    with (run / "quarantine.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert all(row["primary_reason"] == "NVIDIA_SMI_QUERY_PARSE_FAILED" for row in rows)


def test_drift_report_classifies_sensor_drift(tmp_path):
    base = tmp_path / "base"
    current = tmp_path / "current"
    generated_base = runner.invoke(app, ["generate-fixtures", "--output-dir", str(base), "--nodes", "2", "--gpus-per-node", "4", "--scenario", "pass"])
    generated_current = runner.invoke(app, ["generate-fixtures", "--output-dir", str(current), "--nodes", "2", "--gpus-per-node", "4", "--scenario", "sensor_warning"])
    assert generated_base.exit_code == 0, generated_base.output
    assert generated_current.exit_code == 0, generated_current.output
    base_run = base / "run"
    current_run = current / "run"
    for root, run in [(base, base_run), (current, current_run)]:
        result = runner.invoke(
            app,
            [
                "qualify",
                "--evidence",
                str(root / "evidence"),
                "--node-inventory",
                str(root / "node_inventory.yml"),
                "--policy",
                str(root / "qualification_policy.yml"),
                "--output-labels",
                str(run / "labels.csv"),
                "--output-quarantine",
                str(run / "quarantine.csv"),
                "--output-slurm-fragment",
                str(run / "features.conf"),
                "--output-drain-review",
                str(run / "drain_review.sh"),
                "--summary",
                str(run / "summary.json"),
            ],
        )
        assert result.exit_code == 0, result.output
    baseline = runner.invoke(app, ["baseline-create", "--summary", str(base_run / "summary.json"), "--labels", str(base_run / "labels.csv"), "--quarantine", str(base_run / "quarantine.csv"), "--output-baseline", str(base_run / "baseline.json")])
    assert baseline.exit_code == 0, baseline.output
    drift = runner.invoke(app, ["drift-report", "--baseline", str(base_run / "baseline.json"), "--current-summary", str(current_run / "summary.json"), "--current-labels", str(current_run / "labels.csv"), "--current-quarantine", str(current_run / "quarantine.csv"), "--output-json", str(current_run / "drift.json")])
    assert drift.exit_code == 0, drift.output
    report = json.loads((current_run / "drift.json").read_text(encoding="utf-8"))
    assert report["counts"]["sensor_drift_count"] > 0
    assert "sensor_drift" in report["drift_categories"]
