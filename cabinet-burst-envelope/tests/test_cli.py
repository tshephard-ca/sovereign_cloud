from __future__ import annotations

import json

from typer.testing import CliRunner

from cabinet_burst_envelope.cli import app

from .conftest import NOW, generated_power_rows, generated_temperature_rows, write_power_rows, write_profile, write_temperature_rows


def test_cli_estimate_writes_all_outputs(tmp_path):
    profile = write_profile(tmp_path)
    power = write_power_rows(tmp_path, generated_power_rows())
    temp = write_temperature_rows(tmp_path, generated_temperature_rows())
    out = tmp_path / "out"
    result = CliRunner().invoke(
        app,
        [
            "estimate",
            "--power",
            str(power),
            "--temperature",
            str(temp),
            "--cabinet-profile",
            str(profile),
            "--output-envelope",
            str(out / "envelope.json"),
            "--output-timeseries",
            str(out / "aligned.csv"),
            "--output-guardrail",
            str(out / "guardrail.md"),
            "--summary",
            str(out / "summary.json"),
            "--now",
            NOW,
        ],
    )
    assert result.exit_code == 0, result.output
    assert (out / "envelope.json").exists()
    assert (out / "aligned.csv").exists()
    assert (out / "guardrail.md").exists()
    assert (out / "summary.json").exists()


def test_cli_assess_writes_complete_review_packet(tmp_path):
    write_profile(tmp_path)
    write_power_rows(tmp_path, generated_power_rows())
    write_temperature_rows(tmp_path, generated_temperature_rows())
    out = tmp_path / "packet"
    result = CliRunner().invoke(
        app,
        [
            "assess",
            "--case-dir",
            str(tmp_path),
            "--output-dir",
            str(out),
            "--now",
            NOW,
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["review_lane"] == "READY_FOR_FACILITY_REVIEW"
    for filename in [
        "decision.json",
        "action_queue.json",
        "cabinet_review_packet.md",
        "envelope.json",
        "summary.json",
        "aligned_timeseries.csv",
        "facility_review_worksheet.md",
        "manifest.json",
    ]:
        assert (out / filename).exists()
    decision = json.loads((out / "decision.json").read_text(encoding="utf-8"))
    assert decision["business_action"]
    assert decision["conversation_boundary"].startswith("Review-only preflight")
    action_queue = json.loads((out / "action_queue.json").read_text(encoding="utf-8"))
    assert action_queue["actions"]
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["review_lane"]["lane"] == "READY_FOR_FACILITY_REVIEW"
    assert "Decision Card" in (out / "cabinet_review_packet.md").read_text(encoding="utf-8")


def test_cli_assess_redacts_decision_outputs(tmp_path):
    write_profile(tmp_path)
    write_power_rows(tmp_path, generated_power_rows())
    write_temperature_rows(tmp_path, generated_temperature_rows())
    out = tmp_path / "packet"
    result = CliRunner().invoke(
        app,
        [
            "assess",
            "--case-dir",
            str(tmp_path),
            "--output-dir",
            str(out),
            "--now",
            NOW,
            "--redact",
        ],
    )
    assert result.exit_code == 0, result.output
    stdout_payload = json.loads(result.output)
    decision = json.loads((out / "decision.json").read_text(encoding="utf-8"))
    envelope = json.loads((out / "envelope.json").read_text(encoding="utf-8"))
    assert stdout_payload["cabinet_id"] == "cabinet_001"
    assert decision["cabinet_id"] == "cabinet_001"
    assert envelope["review_lane"]["cabinet_id"] == "cabinet_001"


def test_cli_validate_inputs_json(tmp_path):
    profile = write_profile(tmp_path)
    power = write_power_rows(tmp_path, generated_power_rows())
    temp = write_temperature_rows(tmp_path, generated_temperature_rows())
    result = CliRunner().invoke(
        app,
        ["validate-inputs", "--power", str(power), "--temperature", str(temp), "--cabinet-profile", str(profile), "--format", "json", "--now", NOW],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["cabinet_id"] == "cab-test"
    assert "coverage" in payload


def test_cli_lists_policy_packs():
    result = CliRunner().invoke(app, ["policy-packs"])
    assert result.exit_code == 0, result.output
    assert "conservative-air-cooled" in result.output


def test_cli_explain_writes_markdown(tmp_path):
    profile = write_profile(tmp_path)
    power = write_power_rows(tmp_path, generated_power_rows())
    temp = write_temperature_rows(tmp_path, generated_temperature_rows())
    out = tmp_path / "out"
    runner = CliRunner()
    estimate = runner.invoke(
        app,
        ["estimate", "--power", str(power), "--temperature", str(temp), "--cabinet-profile", str(profile), "--output-envelope", str(out / "envelope.json"), "--now", NOW],
    )
    assert estimate.exit_code == 0, estimate.output
    explain = runner.invoke(app, ["explain", "--envelope", str(out / "envelope.json"), "--output-markdown", str(out / "explain.md")])
    assert explain.exit_code == 0, explain.output
    assert "Envelope Explanation" in (out / "explain.md").read_text(encoding="utf-8")


def test_cli_explain_writes_machine_readable_json(tmp_path):
    profile = write_profile(tmp_path)
    power = write_power_rows(tmp_path, generated_power_rows())
    temp = write_temperature_rows(tmp_path, generated_temperature_rows())
    out = tmp_path / "out"
    runner = CliRunner()
    estimate = runner.invoke(
        app,
        ["estimate", "--power", str(power), "--temperature", str(temp), "--cabinet-profile", str(profile), "--output-envelope", str(out / "envelope.json"), "--now", NOW],
    )
    assert estimate.exit_code == 0, estimate.output
    explain = runner.invoke(app, ["explain", "--envelope", str(out / "envelope.json"), "--output-json", str(out / "explain.json")])
    assert explain.exit_code == 0, explain.output
    payload = json.loads((out / "explain.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "cabinet-burst-envelope.explanation.v1"
    assert "calculation_trace" in payload


def test_strict_cli_fails_for_missing_profile(tmp_path):
    power = write_power_rows(tmp_path, generated_power_rows(count=1))
    temp = write_temperature_rows(tmp_path, generated_temperature_rows(count=1))
    result = CliRunner().invoke(
        app,
        ["validate-inputs", "--power", str(power), "--temperature", str(temp), "--cabinet-profile", str(tmp_path / "missing.yml"), "--strict", "--now", NOW],
    )
    assert result.exit_code == 1
