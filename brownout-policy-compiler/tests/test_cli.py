from __future__ import annotations

import json

from typer.testing import CliRunner

from brownout_policy_compiler.cli import app


def test_validate_command_succeeds_for_valid_examples(examples):
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "validate",
            "--event",
            str(examples / "events" / "ddos_event.json"),
            "--services",
            str(examples / "service_priority.yml"),
        ],
    )
    assert result.exit_code == 0
    assert "validation status: PASS" in result.output


def test_compile_command_writes_outputs(tmp_path, examples):
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "compile",
            "--event",
            str(examples / "events" / "ddos_event.json"),
            "--services",
            str(examples / "service_priority.yml"),
            "--output-plan",
            str(tmp_path / "plan.yml"),
            "--output-actions",
            str(tmp_path / "actions.csv"),
            "--output-rollback",
            str(tmp_path / "rollback.yml"),
            "--summary",
            str(tmp_path / "summary.json"),
            "--incident-id",
            "INC-12345",
            "--now",
            "2026-01-01T00:05:00Z",
        ],
    )
    assert result.exit_code == 0
    assert (tmp_path / "plan.yml").exists()
    assert (tmp_path / "decision_brief.json").exists()
    assert (tmp_path / "decision_brief.md").exists()
    assert (tmp_path / "operator_queue.csv").exists()
    assert (tmp_path / "approval_queue.csv").exists()
    assert (tmp_path / "rollback_clock.json").exists()
    assert (tmp_path / "blocked_actions.json").exists()
    decision_brief = json.loads((tmp_path / "decision_brief.json").read_text())
    assert decision_brief["business_throughline"]["message"].startswith("Preserve critical")
    assert "protect_now_count" in decision_brief["first_read"]
    assert "review package status:" in result.output


def test_explain_command_writes_markdown_summary(tmp_path, examples):
    runner = CliRunner()
    plan = tmp_path / "plan.yml"
    compile_result = runner.invoke(
        app,
        [
            "compile",
            "--event",
            str(examples / "events" / "ddos_event.json"),
            "--services",
            str(examples / "service_priority.yml"),
            "--output-plan",
            str(plan),
            "--output-actions",
            str(tmp_path / "actions.csv"),
            "--output-rollback",
            str(tmp_path / "rollback.yml"),
            "--summary",
            str(tmp_path / "summary.json"),
            "--incident-id",
            "INC-12345",
            "--now",
            "2026-01-01T00:05:00Z",
        ],
    )
    assert compile_result.exit_code == 0
    result = runner.invoke(app, ["explain", "--plan", str(plan), "--output-markdown", str(tmp_path / "summary.md")])
    assert result.exit_code == 0
    assert (tmp_path / "summary.md").exists()


def test_no_test_performs_network_calls(monkeypatch, compile_options_factory):
    import socket

    def fail(*args, **kwargs):
        raise AssertionError("network calls are not expected")

    monkeypatch.setattr(socket, "socket", fail)
    from brownout_policy_compiler.compile_rules import compile_from_paths

    result = compile_from_paths(compile_options_factory())
    assert result.plan.mode == "REVIEW_ONLY"
