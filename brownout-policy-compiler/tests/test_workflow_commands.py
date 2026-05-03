from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from brownout_policy_compiler.cli import app


def test_init_all_generates_required_input_data(tmp_path):
    runner = CliRunner()
    seed = tmp_path / "seed"
    result = runner.invoke(app, ["init", "all", "--output-dir", str(seed)])
    assert result.exit_code == 0
    assert (seed / "service_priority.yml").exists()
    assert (seed / "policy_pack.yml").exists()
    assert (seed / "thresholds.yml").exists()
    assert (seed / "endpoint_inventory.csv").exists()
    assert (seed / "approval_matrix.yml").exists()
    assert (seed / "rollback_controls.yml").exists()
    assert (seed / "events" / "01_volumetric_public_and_vpn.json").exists()
    manifest = json.loads((seed / "input_manifest.json").read_text())
    assert manifest["input_seed_bundle_version"] == 1
    assert len(manifest["events"]) == 18


def test_generate_single_event_and_catalog(tmp_path):
    runner = CliRunner()
    event_path = tmp_path / "event.json"
    result = runner.invoke(
        app,
        ["generate", "event", "--scenario", "application_payment_endpoint", "--output", str(event_path)],
    )
    assert result.exit_code == 0
    event = json.loads(event_path.read_text())
    assert event["attack_class"] == "APPLICATION"
    assert event["event_id"] == "evt-gen-002"

    catalog_path = tmp_path / "catalog.yml"
    catalog_result = runner.invoke(app, ["generate", "scenario-catalog", "--output", str(catalog_path)])
    assert catalog_result.exit_code == 0
    catalog = yaml.safe_load(catalog_path.read_text())
    assert len(catalog["scenarios"]) == 18


def test_readiness_command_scores_generated_service_priority(tmp_path):
    runner = CliRunner()
    seed = tmp_path / "seed"
    assert runner.invoke(app, ["init", "all", "--output-dir", str(seed)]).exit_code == 0
    output = tmp_path / "readiness.json"
    result = runner.invoke(app, ["readiness", "--services", str(seed / "service_priority.yml"), "--output", str(output)])
    assert result.exit_code == 0
    report = json.loads(output.read_text())
    assert report["readiness_report_version"] == 1
    assert report["review_package_readiness_score"] == 100.0
    assert report["status"] == "READY_FOR_TABLETOP"
    assert report["priority_counts"]["P0"] >= 1


def test_tabletop_command_writes_review_bundle(tmp_path):
    runner = CliRunner()
    seed = tmp_path / "seed"
    assert runner.invoke(app, ["init", "all", "--output-dir", str(seed)]).exit_code == 0
    output_dir = tmp_path / "tabletop"
    result = runner.invoke(
        app,
        [
            "tabletop",
            "--event",
            str(seed / "events" / "01_volumetric_public_and_vpn.json"),
            "--services",
            str(seed / "service_priority.yml"),
            "--policy-pack",
            str(seed / "policy_pack.yml"),
            "--config",
            str(seed / "thresholds.yml"),
            "--output-dir",
            str(output_dir),
            "--incident-id",
            "INC-TABLETOP-001",
            "--now",
            "2026-01-01T00:05:00Z",
        ],
    )
    assert result.exit_code == 0
    assert (output_dir / "brownout_plan.yml").exists()
    assert (output_dir / "actions.csv").exists()
    assert (output_dir / "rollback_plan.yml").exists()
    assert (output_dir / "summary.json").exists()
    assert "# Brownout Tabletop Run" in (output_dir / "tabletop_report.md").read_text()


def test_post_incident_diff_command_compares_actual_changes(tmp_path):
    runner = CliRunner()
    seed = tmp_path / "seed"
    assert runner.invoke(app, ["init", "all", "--output-dir", str(seed)]).exit_code == 0
    tabletop_dir = tmp_path / "tabletop"
    tabletop_result = runner.invoke(
        app,
        [
            "tabletop",
            "--event",
            str(seed / "events" / "06_low_priority_null_route_candidate.json"),
            "--services",
            str(seed / "service_priority.yml"),
            "--policy-pack",
            str(seed / "policy_pack.yml"),
            "--config",
            str(seed / "thresholds.yml"),
            "--output-dir",
            str(tabletop_dir),
            "--incident-id",
            "INC-GEN-006",
            "--now",
            "2026-01-01T00:05:00Z",
            "--allow-null-route",
        ],
    )
    assert tabletop_result.exit_code == 0
    actual_changes = tmp_path / "actual_changes.yml"
    actual_changes.write_text(
        yaml.safe_dump(
            {
                "post_incident_diff_version": 1,
                "incident_id": "INC-GEN-006",
                "actual_changes": [
                    {
                        "action_id": "act_001",
                        "status": "applied",
                        "applied_at": "2026-01-01T00:06:00Z",
                        "rollback_evidence": "operator-entered rollback confirmation",
                    }
                ],
            },
            sort_keys=False,
        )
    )
    output = tmp_path / "diff.json"
    result = runner.invoke(
        app,
        [
            "post-incident-diff",
            "--plan",
            str(tabletop_dir / "brownout_plan.yml"),
            "--actual-changes",
            str(actual_changes),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0
    diff = json.loads(output.read_text())
    assert diff["post_incident_diff_version"] == 1
    assert diff["actions_applied"] == 1
    assert diff["actions_not_recorded"] >= 0
