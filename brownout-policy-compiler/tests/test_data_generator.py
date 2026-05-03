from __future__ import annotations

from typer.testing import CliRunner

from brownout_policy_compiler.cli import app
from brownout_policy_compiler.data_generator import generate_realistic_bundle


def test_generate_realistic_bundle_creates_inputs_outputs_and_gap_report(tmp_path):
    coverage = generate_realistic_bundle(tmp_path / "bundle")
    assert coverage["input"]["scenario_count"] == 18
    assert coverage["output"]["scenario_outputs"] == 18
    assert coverage["output"]["action_count"] > 0
    assert (tmp_path / "bundle" / "inputs" / "service_priority.yml").exists()
    assert (tmp_path / "bundle" / "inputs" / "endpoint_inventory.csv").exists()
    assert (tmp_path / "bundle" / "inputs" / "service_priority_questions.md").exists()
    assert (tmp_path / "bundle" / "schemas" / "ddos_event.schema.json").exists()
    assert (tmp_path / "bundle" / "fingerprints.json").exists()
    assert (tmp_path / "bundle" / "coverage_report.json").exists()
    assert (tmp_path / "bundle" / "gap_report.md").exists()
    assert (tmp_path / "bundle" / "realism_report.json").exists()
    assert (tmp_path / "bundle" / "redacted_inputs" / "service_priority.yml").exists()
    assert (tmp_path / "bundle" / "inputs" / "negative" / "service_priority_invalid_p0_shed.yml").exists()
    assert (tmp_path / "bundle" / "inputs" / "large_estate" / "service_priority_100.yml").exists()
    assert not coverage["output"]["forbidden_term_findings"]
    assert coverage["realism"]["status"] == "REALISM_GAPS_CLOSED"


def test_generate_data_cli_command(tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["generate-data", "--output-dir", str(tmp_path / "bundle")])
    assert result.exit_code == 0
    assert "compiled scenarios: 18" in result.output
    assert (tmp_path / "bundle" / "manifest.json").exists()


def test_lab_generate_bundle_cli_command(tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["lab", "generate-bundle", "--output-dir", str(tmp_path / "bundle")])
    assert result.exit_code == 0
    assert "generated lab bundle:" in result.output
    assert "compiled scenarios: 18" in result.output
    assert (tmp_path / "bundle" / "manifest.json").exists()
