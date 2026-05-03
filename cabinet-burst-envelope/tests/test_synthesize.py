from __future__ import annotations

import json

import yaml
from typer.testing import CliRunner

from cabinet_burst_envelope.cli import app
from cabinet_burst_envelope.synthesize import list_scenarios


def test_synthesize_generates_complete_scenario_with_expected_envelope(tmp_path):
    out = tmp_path / "scenario"
    result = CliRunner().invoke(
        app,
        ["synthesize", "--scenario", "healthy_margin", "--output-dir", str(out), "--seed", "11"],
    )
    assert result.exit_code == 0, result.output
    assert (out / "pdu_power.csv").exists()
    assert (out / "inlet_temps.csv").exists()
    assert (out / "cabinet_profile.yml").exists()
    assert (out / "thresholds.yml").exists()
    assert (out / "case_manifest.yml").exists()
    assert (out / "scenario_manifest.yml").exists()
    envelope = json.loads((out / "expected_envelope.json").read_text(encoding="utf-8"))
    manifest = yaml.safe_load((out / "scenario_manifest.yml").read_text(encoding="utf-8"))
    case_manifest = yaml.safe_load((out / "case_manifest.yml").read_text(encoding="utf-8"))
    assert envelope["schema_version"] == "cabinet-burst-envelope.envelope.v1"
    assert envelope["envelope_status"] == "READY_FOR_REVIEW"
    assert envelope["evidence_quality"]["score"] >= 85
    assert manifest["schema_version"] == "cabinet-burst-envelope.scenario.v1"
    assert manifest["files"]["case_manifest"] == "case_manifest.yml"
    assert case_manifest["expected_review_lane"] == "READY_FOR_FACILITY_REVIEW"


def test_synthesize_lists_and_generates_all_required_scenarios(tmp_path):
    runner = CliRunner()
    listing = runner.invoke(app, ["synthesize", "--list"])
    assert listing.exit_code == 0, listing.output
    assert "healthy_margin" in listing.output
    assert set(list_scenarios()) >= {
        "healthy_margin",
        "electrical_limited",
        "thermal_limited",
        "missing_top_sensor",
        "feed_imbalance_critical",
        "missing_electrical_limits",
        "missing_thermal_limits",
    }

    out = tmp_path / "all"
    result = runner.invoke(app, ["synthesize", "--all", "--output-dir", str(out), "--days", "1", "--no-write-expected-envelope"])
    assert result.exit_code == 0, result.output
    generated = {path.name for path in out.iterdir() if path.is_dir()}
    assert set(list_scenarios()) == generated


def test_benchmark_generates_and_checks_synthetic_corpus(tmp_path):
    result = CliRunner().invoke(app, ["benchmark", "--output-dir", str(tmp_path / "benchmark"), "--days", "1", "--seed", "13"])
    assert result.exit_code == 0, result.output
    payload = json.loads((tmp_path / "benchmark" / "benchmark.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "cabinet-burst-envelope.benchmark.v1"
    assert payload["scenario_count"] == len(list_scenarios())
    assert payload["passed"] is True
    assert set(payload["output_coverage"]["review_lane_counts"]) >= {
        "READY_FOR_FACILITY_REVIEW",
        "NEEDS_REMEDIATION",
        "STOP_EXPANSION_DISCUSSION",
        "COLLECT_EVIDENCE",
    }
    healthy = next(row for row in payload["results"] if row["scenario"] == "healthy_margin")
    assert healthy["confidence"] == "HIGH"
