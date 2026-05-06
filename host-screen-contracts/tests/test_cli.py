from __future__ import annotations

import json
from pathlib import Path
import sys
import zipfile

import yaml
from typer.testing import CliRunner

from host_screen_contracts.cli import app
from host_screen_contracts.contract_model import contract_to_dict
from host_screen_contracts.flow_extract import extract_transaction
from host_screen_contracts.field_map import load_field_map
from host_screen_contracts.parse_trace import load_trace

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_cli_extract_command_produces_all_requested_files(tmp_path):
    runner = CliRunner()
    contract = tmp_path / "order_lookup.contract.yml"
    openapi = tmp_path / "order_lookup.openapi.yml"
    replay_test = tmp_path / "test_order_lookup_replay.py"
    replay_case = tmp_path / "order_lookup.case.yml"
    summary = tmp_path / "order_lookup.summary.json"
    result = runner.invoke(
        app,
        [
            "extract",
            "--trace",
            str(EXAMPLES / "order_lookup.trace.jsonl"),
            "--field-map",
            str(EXAMPLES / "order_lookup.fields.yml"),
            "--transaction-id",
            "order_lookup",
            "--output-contract",
            str(contract),
            "--output-openapi",
            str(openapi),
            "--output-replay-test",
            str(replay_test),
            "--output-replay-case",
            str(replay_case),
            "--summary",
            str(summary),
        ],
    )
    assert result.exit_code == 0, result.output
    assert contract.exists()
    assert openapi.exists()
    assert replay_test.exists()
    assert replay_case.exists()
    assert summary.exists()

    result = runner.invoke(
        app,
        [
            "replay",
            "--trace",
            str(EXAMPLES / "order_lookup.trace.jsonl"),
            "--contract",
            str(contract),
            "--case",
            str(replay_case),
        ],
    )
    assert result.exit_code == 0, result.output
    assert '"ok": true' in result.output

    replay_data = yaml.safe_load(replay_case.read_text())
    bad_start = tmp_path / "bad_start.case.yml"
    bad_start.write_text(yaml.safe_dump({**replay_data, "start_screen_hash": "bad"}))
    result = runner.invoke(app, ["replay", "--trace", str(EXAMPLES / "order_lookup.trace.jsonl"), "--contract", str(contract), "--case", str(bad_start)])
    assert result.exit_code == 1
    assert "start screen hash mismatch" in result.output

    bad_expect = tmp_path / "bad_expect.case.yml"
    bad_expect_data = yaml.safe_load(replay_case.read_text())
    bad_expect_data["steps"][0]["expect_screen_hash"] = "bad"
    bad_expect.write_text(yaml.safe_dump(bad_expect_data))
    result = runner.invoke(app, ["replay", "--trace", str(EXAMPLES / "order_lookup.trace.jsonl"), "--contract", str(contract), "--case", str(bad_expect)])
    assert result.exit_code == 1
    assert "expected screen hash mismatch" in result.output

    bad_next = tmp_path / "bad_next.case.yml"
    bad_next_data = yaml.safe_load(replay_case.read_text())
    bad_next_data["steps"][0]["expect_next_screen_hash"] = "bad"
    bad_next.write_text(yaml.safe_dump(bad_next_data))
    result = runner.invoke(app, ["replay", "--trace", str(EXAMPLES / "order_lookup.trace.jsonl"), "--contract", str(contract), "--case", str(bad_next)])
    assert result.exit_code == 1
    assert "next screen hash mismatch" in result.output

    bad_response = tmp_path / "bad_response.case.yml"
    bad_response_data = yaml.safe_load(replay_case.read_text())
    bad_response_data["expected_response"]["customer_name"] = "WRONG"
    bad_response.write_text(yaml.safe_dump(bad_response_data))
    result = runner.invoke(app, ["replay", "--trace", str(EXAMPLES / "order_lookup.trace.jsonl"), "--contract", str(contract), "--case", str(bad_response)])
    assert result.exit_code == 1
    assert "response mismatch for customer_name" in result.output

    result = runner.invoke(
        app,
        [
            "validate-openapi",
            "--openapi",
            str(openapi),
            "--external-validator-command",
            f'{sys.executable} -c "import sys; sys.exit(0)"',
        ],
    )
    assert result.exit_code == 0, result.output
    assert '"skipped": false' in result.output


def test_cli_validate_trace_reports_ok():
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["validate-trace", "--trace", str(EXAMPLES / "order_lookup.trace.jsonl"), "--strict"],
    )
    assert result.exit_code == 0, result.output
    assert '"ok": true' in result.output

    result = runner.invoke(
        app,
        ["validate-trace", "--trace", str(EXAMPLES / "order_lookup.trace.jsonl"), "--screen-size", "24x80"],
    )
    assert result.exit_code == 0

    result = runner.invoke(
        app,
        ["validate-trace", "--trace", str(EXAMPLES / "order_lookup.trace.jsonl"), "--screen-size", "bad"],
    )
    assert result.exit_code != 0


def test_cli_real_world_data_commands(tmp_path):
    runner = CliRunner()
    sanitized = tmp_path / "customer.sanitized.jsonl"
    privacy = tmp_path / "privacy.json"
    result = runner.invoke(
        app,
        [
            "sanitize-trace",
            "--trace",
            str(EXAMPLES / "customer_update.trace.jsonl"),
            "--field-map",
            str(EXAMPLES / "customer_update.fields.yml"),
            "--output",
            str(sanitized),
            "--report",
            str(privacy),
        ],
    )
    assert result.exit_code == 0, result.output
    assert sanitized.exists()
    assert privacy.exists()

    labels = tmp_path / "labels.yml"
    result = runner.invoke(
        app,
        [
            "label-sheet",
            "--trace",
            str(EXAMPLES / "order_lookup.trace.jsonl"),
            "--field-map",
            str(EXAMPLES / "order_lookup.fields.yml"),
            "--output",
            str(labels),
        ],
    )
    assert result.exit_code == 0, result.output
    assert yaml.safe_load(labels.read_text())["field_count"] >= 3


def test_cli_generated_corpus_workflow_handles_low_confidence_non_strictly(tmp_path):
    runner = CliRunner()
    corpus = tmp_path / "corpus"
    result = runner.invoke(app, ["generate-corpus", "--output", str(corpus)])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["coverage-report", "--package-root", str(corpus)])
    assert result.exit_code == 0, result.output
    assert '"complete": true' in result.output
    result = runner.invoke(app, ["realism-report", "--package-root", str(corpus)])
    assert result.exit_code == 0, result.output
    assert '"synthetic_package_count": 9' in result.output

    output_dir = tmp_path / "low_confidence_out"
    result = runner.invoke(
        app,
        ["extract-package", "--package", str(corpus / "synthetic_low_confidence_guardrail"), "--output-dir", str(output_dir)],
    )
    assert result.exit_code == 0, result.output
    assert '"ok": false' in result.output

    result = runner.invoke(
        app,
        [
            "extract-package",
            "--package",
            str(corpus / "synthetic_low_confidence_guardrail"),
            "--output-dir",
            str(tmp_path / "low_confidence_strict_out"),
            "--strict",
        ],
    )
    assert result.exit_code == 1, result.output

    review_dir = tmp_path / "order_review"
    result = runner.invoke(
        app,
        [
            "review-package",
            "--package",
            str(corpus / "synthetic_order_inquiry_multi_case"),
            "--output-dir",
            str(review_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert '"review_package_status": "review_required"' in result.output
    assert (review_dir / "readiness.json").exists()
    assert (review_dir / "executive_summary.md").exists()
    assert (review_dir / "review_package.zip").exists()
    with zipfile.ZipFile(review_dir / "review_package.zip") as archive:
        names = set(archive.namelist())
        assert {"contract.yml", "openapi.yml", "replay_case.yml", "replay_test.py", "drift_evidence.yml", "flow_graph.yml"}.issubset(names)
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["completeness"]["score"] == 100


def test_cli_compare_mutate_dataset_benchmark_and_bundle(tmp_path):
    runner = CliRunner()
    events = load_trace(EXAMPLES / "order_lookup.trace.jsonl")
    fmap = load_field_map(EXAMPLES / "order_lookup.fields.yml")
    extraction = extract_transaction(events, transaction_id="order_lookup", field_map=fmap)
    contract = tmp_path / "contract.yml"
    contract.write_text(yaml.safe_dump(contract_to_dict(extraction.contract), sort_keys=False))

    drift_trace = tmp_path / "drift.trace.jsonl"
    result = runner.invoke(
        app,
        [
            "mutate-trace",
            "--trace",
            str(EXAMPLES / "order_lookup.trace.jsonl"),
            "--output",
            str(drift_trace),
            "--change-label",
            "Status:State",
        ],
    )
    assert result.exit_code == 0, result.output

    drift = tmp_path / "drift.json"
    result = runner.invoke(
        app,
        [
            "compare",
            "--contract",
            str(contract),
            "--trace",
            str(drift_trace),
            "--field-map",
            str(EXAMPLES / "order_lookup.fields.yml"),
            "--output",
            str(drift),
        ],
    )
    assert result.exit_code == 0, result.output
    assert '"status": "review_required"' in result.output

    package = tmp_path / "pkg"
    result = runner.invoke(app, ["dataset", "init", "--package", str(package), "--transaction-id", "order_lookup"])
    assert result.exit_code == 0, result.output
    (package / "traces" / "happy_path.trace.jsonl").write_text((EXAMPLES / "order_lookup.trace.jsonl").read_text())
    (package / "field_maps" / "transaction.fields.yml").write_text((EXAMPLES / "order_lookup.fields.yml").read_text())
    result = runner.invoke(app, ["dataset", "validate", "--package", str(package)])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["benchmark", "--package", str(package), "--output", str(tmp_path / "benchmark.json")])
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        app,
        ["dataset", "benchmark", "--package", str(package), "--output", str(tmp_path / "dataset_benchmark.json")],
    )
    assert result.exit_code == 0, result.output

    summary = tmp_path / "summary.json"
    summary.write_text("{}")
    bundle = tmp_path / "handoff.zip"
    result = runner.invoke(
        app,
        ["bundle", "--output", str(bundle), "--contract", str(contract), "--summary", str(summary)],
    )
    assert result.exit_code == 0, result.output
    assert '"score": 45' in result.output
    with zipfile.ZipFile(bundle) as archive:
        assert "manifest.json" in archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["completeness"]["score"] == 45

    result = runner.invoke(app, ["bundle-score", "--bundle", str(bundle)])
    assert result.exit_code == 0, result.output
    assert '"level": "partial"' in result.output


def test_cli_error_and_report_branches(tmp_path):
    runner = CliRunner()
    no_screen_trace = tmp_path / "no_screen.trace.jsonl"
    no_screen_trace.write_text('{"type":"action","seq":1,"aid":"ENTER","inputs":[]}\n')
    result = runner.invoke(app, ["validate-trace", "--trace", str(no_screen_trace), "--strict"])
    assert result.exit_code == 1
    assert "NO_SCREEN_EVENTS" in result.output

    result = runner.invoke(
        app,
        [
            "extract",
            "--trace",
            str(no_screen_trace),
            "--transaction-id",
            "bad",
            "--output-contract",
            str(tmp_path / "bad.contract.yml"),
            "--output-openapi",
            str(tmp_path / "bad.openapi.yml"),
            "--output-replay-test",
            str(tmp_path / "test_bad.py"),
            "--summary",
            str(tmp_path / "bad.summary.json"),
            "--strict",
        ],
    )
    assert result.exit_code == 1
    assert "NO_SCREEN_EVENTS" in result.output

    invalid_openapi = tmp_path / "invalid.openapi.yml"
    invalid_openapi.write_text("openapi: 3.0.0\ninfo: {}\npaths: {}\n")
    openapi_report = tmp_path / "openapi-report.json"
    result = runner.invoke(app, ["validate-openapi", "--openapi", str(invalid_openapi), "--output", str(openapi_report)])
    assert result.exit_code == 1
    assert openapi_report.exists()
    assert "OPENAPI_VERSION_NOT_3_1_0" in result.output

    privacy = tmp_path / "privacy.json"
    result = runner.invoke(
        app,
        [
            "privacy-report",
            "--trace",
            str(EXAMPLES / "customer_update.trace.jsonl"),
            "--field-map",
            str(EXAMPLES / "customer_update.fields.yml"),
            "--output",
            str(privacy),
            "--fail-on-sensitive-unredacted",
        ],
    )
    assert result.exit_code == 1
    assert privacy.exists()

    result = runner.invoke(
        app,
        [
            "mutate-trace",
            "--trace",
            str(EXAMPLES / "order_lookup.trace.jsonl"),
            "--output",
            str(tmp_path / "bad-mutate.trace.jsonl"),
            "--change-label",
            "missing-separator",
        ],
    )
    assert result.exit_code != 0

    adversarial = tmp_path / "adversarial"
    result = runner.invoke(app, ["generate-adversarial-corpus", "--output", str(adversarial)])
    assert result.exit_code == 0
    assert (adversarial / "adversarial.json").exists()

    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    result = runner.invoke(app, ["coverage-report", "--package-root", str(incomplete), "--output", str(tmp_path / "coverage.json")])
    assert result.exit_code == 1
    assert '"complete": false' in result.output

    result = runner.invoke(app, ["realism-report"])
    assert result.exit_code != 0

    corpus = tmp_path / "corpus"
    result = runner.invoke(app, ["generate-corpus", "--output", str(corpus)])
    assert result.exit_code == 0
    package_report = tmp_path / "package-realism.json"
    result = runner.invoke(
        app,
        ["realism-report", "--package", str(corpus / "synthetic_order_inquiry_multi_case"), "--output", str(package_report)],
    )
    assert result.exit_code == 0
    assert package_report.exists()

    bundle = tmp_path / "empty-ish.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.json", "{}")
    score_output = tmp_path / "bundle-score.json"
    result = runner.invoke(app, ["bundle-score", "--bundle", str(bundle), "--output", str(score_output)])
    assert result.exit_code == 0
    assert score_output.exists()


def test_cli_record_manual_writes_offline_trace(tmp_path):
    runner = CliRunner()
    output = tmp_path / "manual.trace.jsonl"
    result = runner.invoke(
        app,
        ["record-manual", "--output", str(output), "--rows", "24", "--cols", "80"],
        input=(
            "FIRST SCREEN\n"
            ".\n"
            "y\n"
            "1\n"
            "1\n"
            "5\n"
            "y\n"
            "HELLO\n"
            "n\n"
            "y\n"
            "ENTER\n"
            "y\n"
            "f_01_01\n"
            "1\n"
            "1\n"
            "HELLO\n"
            "n\n"
            "SECOND SCREEN\n"
            ".\n"
            "n\n"
            "n\n"
        ),
    )
    assert result.exit_code == 0, result.output
    events = [json.loads(line) for line in output.read_text().splitlines()]
    assert [event["type"] for event in events] == ["screen", "action", "screen"]
    assert events[0]["fields"][0]["protected"] is True
