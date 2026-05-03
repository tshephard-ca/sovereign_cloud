import csv
import json
import os
from pathlib import Path

from typer.testing import CliRunner

from gpu_rack_qualifier.cli import app
from gpu_rack_qualifier.action_queue import REVIEW_QUEUE_COLUMNS
from gpu_rack_qualifier.report import LABEL_COLUMNS, QUARANTINE_COLUMNS


runner = CliRunner()


def test_cli_qualify_writes_expected_outputs(tmp_path):
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
        ],
    )
    assert result.exit_code == 0, result.output
    with (out / "labels.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == LABEL_COLUMNS
        rows = list(reader)
    with (out / "quarantine.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == QUARANTINE_COLUMNS
    with (out / "review_queue.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == REVIEW_QUEUE_COLUMNS
        assert all(row["readiness_lane"] != "MULTINODE_READY" for row in reader)
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["qualification"]["PASS"] == 2
    assert summary["readiness"]["MULTINODE_READY"] == 2
    assert summary["action_queue_counts"]["total"] == 2
    assert rows == sorted(rows, key=lambda row: row["node_name"])
    assert not (os.stat(out / "drain_review.sh").st_mode & os.X_OK)
    assert all(line.startswith("#") for line in (out / "features.conf").read_text(encoding="utf-8").splitlines())
    assert "ReadinessLane=" in (out / "features.conf").read_text(encoding="utf-8")
    assert all(line.startswith("#") or line.startswith("#!") for line in (out / "drain_review.sh").read_text(encoding="utf-8").splitlines())


def test_cli_explain_writes_markdown(tmp_path):
    out = tmp_path / "out"
    qualify_result = runner.invoke(
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
        ],
    )
    assert qualify_result.exit_code == 0
    explain_result = runner.invoke(
        app,
        [
            "explain",
            "--summary",
            str(out / "summary.json"),
            "--labels",
            str(out / "labels.csv"),
            "--quarantine",
            str(out / "quarantine.csv"),
            "--output-markdown",
            str(out / "summary.md"),
        ],
    )
    assert explain_result.exit_code == 0, explain_result.output
    assert "review-only" in (out / "summary.md").read_text(encoding="utf-8")


def test_strict_mode_fails_on_missing_required_evidence(tmp_path):
    evidence = tmp_path / "evidence"
    (evidence / "node-a").mkdir(parents=True)
    result = runner.invoke(app, ["validate-evidence", "--evidence", str(evidence), "--strict"])
    assert result.exit_code != 0
    assert "missing nccl_single_node_all_reduce.txt" in result.output


def test_non_strict_mode_produces_review_for_partial_evidence(tmp_path):
    evidence = tmp_path / "evidence"
    (evidence / "node-a").mkdir(parents=True)
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "qualify",
            "--evidence",
            str(evidence),
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
        ],
    )
    assert result.exit_code == 0, result.output
    with (out / "labels.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["qualification_status"] == "REVIEW"


def test_redacted_cli_output_hides_node_names(tmp_path):
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
            "--redact",
        ],
    )
    assert result.exit_code == 0, result.output
    labels_text = (out / "labels.csv").read_text(encoding="utf-8")
    assert "gpu001" not in labels_text
    assert "node_001" in labels_text


def test_tests_do_not_run_scontrol_or_network_calls():
    source = "\n".join(path.read_text(encoding="utf-8") for path in Path("src/gpu_rack_qualifier").glob("*.py"))
    assert "requests." not in source
    assert "urllib.request" not in source
    assert "socket." not in source
    assert "scontrol update" not in Path("src/gpu_rack_qualifier/collect_local.py").read_text(encoding="utf-8")
