import csv
from pathlib import Path

from typer.testing import CliRunner

from estate_triage.cli import app, run_analysis
from estate_triage.report import OUTPUT_COLUMNS


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
RUNNER = CliRunner()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_examples_write_top_25_and_summary(tmp_path):
    output = tmp_path / "top25.csv"
    summary = tmp_path / "summary.json"

    result = run_analysis(
        inventory_path=EXAMPLES / "inventory.csv",
        backup_path=EXAMPLES / "backup_export.csv",
        output_path=output,
        summary_path=summary,
        top_n_override=25,
    )

    rows = read_rows(output)
    assert len(rows) == 25
    assert result["input"]["inventory_rows"] == 25
    assert result["input"]["backup_rows"] == 25
    assert result["output"]["rows_written"] == 25
    assert result["output"]["ranking_mode"] == "balanced"
    assert result["business_impact"]["presentation_counts"]["strong_candidate"] > 0
    assert summary.exists()


def test_default_demo_output_has_business_motion_balance(tmp_path):
    output = tmp_path / "top25.csv"
    summary = tmp_path / "summary.json"

    result = run_analysis(
        inventory_path=EXAMPLES / "inventory.csv",
        backup_path=EXAMPLES / "backup_export.csv",
        utilization_path=EXAMPLES / "utilization.csv",
        output_path=output,
        summary_path=summary,
        top_n_override=25,
    )

    rows = read_rows(output)
    ranked_motions = {row["primary_motion"] for row in rows}
    assert ranked_motions >= {
        "MIGRATION_REVIEW",
        "ARCHIVE_REVIEW",
        "RIGHTSIZING_REVIEW",
        "DR_TIER_REVIEW",
    }
    assert result["motions"]["ARCHIVE_REVIEW"] > 0
    assert result["motions"]["RIGHTSIZING_REVIEW"] > 0
    assert result["motions"]["DR_TIER_REVIEW"] > 0
    assert result["business_impact"]["presentation_counts"]["needs_more_data"] > 0
    assert result["business_impact"]["presentation_counts"]["do_not_present"] > 0


def test_output_column_order_is_exact(tmp_path):
    output = tmp_path / "top25.csv"
    run_analysis(
        inventory_path=EXAMPLES / "inventory.csv",
        backup_path=EXAMPLES / "backup_export.csv",
        output_path=output,
        top_n_override=25,
    )

    header = output.read_text(encoding="utf-8").splitlines()[0].split(",")
    assert header == OUTPUT_COLUMNS


def test_ranking_is_deterministic(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"

    kwargs = {
        "inventory_path": EXAMPLES / "inventory.csv",
        "backup_path": EXAMPLES / "backup_export.csv",
        "top_n_override": 25,
    }
    run_analysis(output_path=first, **kwargs)
    run_analysis(output_path=second, **kwargs)

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def test_redact_hides_workload_names_and_hashes_keys(tmp_path):
    output = tmp_path / "redacted.csv"
    result = RUNNER.invoke(
        app,
        [
            "analyze",
            "--inventory",
            str(EXAMPLES / "inventory.csv"),
            "--backup",
            str(EXAMPLES / "backup_export.csv"),
            "--output",
            str(output),
            "--top-n",
            "5",
            "--redact",
        ],
    )

    assert result.exit_code == 0, result.output
    rows = read_rows(output)
    assert rows[0]["workload_name"].startswith("workload_")
    assert "app-" not in output.read_text(encoding="utf-8")
    assert len(rows[0]["workload_key"]) == 12
    int(rows[0]["workload_key"], 16)


def test_strict_fails_on_missing_required_name_column(tmp_path):
    inventory = tmp_path / "inventory.csv"
    backup = tmp_path / "backup.csv"
    output = tmp_path / "out.csv"
    inventory.write_text("CPUs,Memory MiB\n2,4096\n", encoding="utf-8")
    backup.write_text(
        "VM,backup_total_mib\nworkload,100\n",
        encoding="utf-8",
    )

    result = RUNNER.invoke(
        app,
        [
            "analyze",
            "--inventory",
            str(inventory),
            "--backup",
            str(backup),
            "--output",
            str(output),
            "--strict",
        ],
    )

    assert result.exit_code == 1
    assert "missing a workload name column" in result.output
