import csv
import json

from typer.testing import CliRunner

from stateful_storage_fit.cli import app
from stateful_storage_fit.report import MOUNT_CSV_COLUMNS

from tests.helpers import DF_DATA, FSTAB_DATA, IOSTAT_LOW, MOUNT_DATA, PROFILE, PS_DB


runner = CliRunner()


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_strict_mode_fails_on_missing_df(tmp_path):
    profile = _write(tmp_path / "profile.yml", PROFILE)
    result = runner.invoke(
        app,
        [
            "check",
            "--strict",
            "--mount",
            str(_write(tmp_path / "mount.txt", MOUNT_DATA)),
            "--storage-profile",
            str(profile),
        ],
    )
    assert result.exit_code != 0
    assert "df" in result.output


def test_strict_mode_fails_on_invalid_storage_profile(tmp_path):
    df = _write(tmp_path / "df.txt", DF_DATA)
    mount = _write(tmp_path / "mount.txt", MOUNT_DATA)
    bad_profile = _write(tmp_path / "profile.yml", "storage_classes: []\nperformance_tiers: {}\n")
    result = runner.invoke(
        app,
        ["check", "--strict", "--df", str(df), "--mount", str(mount), "--storage-profile", str(bad_profile)],
    )
    assert result.exit_code != 0
    assert "storage profile" in result.output


def test_cli_writes_json_and_mount_csv_with_requested_columns(tmp_path):
    df = _write(tmp_path / "df.txt", DF_DATA)
    mount = _write(tmp_path / "mount.txt", MOUNT_DATA)
    fstab = _write(tmp_path / "fstab.txt", FSTAB_DATA)
    iostat = _write(tmp_path / "iostat.txt", IOSTAT_LOW)
    ps = _write(tmp_path / "ps.txt", PS_DB)
    profile = _write(tmp_path / "profile.yml", PROFILE)
    output = tmp_path / "out" / "fit.json"
    mount_report = tmp_path / "out" / "mounts.csv"
    result = runner.invoke(
        app,
        [
            "check",
            "--df",
            str(df),
            "--mount",
            str(mount),
            "--fstab",
            str(fstab),
            "--iostat",
            str(iostat),
            "--ps",
            str(ps),
            "--storage-profile",
            str(profile),
            "--output",
            str(output),
            "--mount-report",
            str(mount_report),
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["fit_status"] == "PASS"
    with mount_report.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        assert next(reader) == MOUNT_CSV_COLUMNS


def test_cli_portfolio_and_corpus_commands_write_json(tmp_path):
    portfolio_output = tmp_path / "portfolio.json"
    corpus_output = tmp_path / "corpus.json"
    portfolio_result = runner.invoke(
        app,
        ["portfolio", "--inventory", "examples/portfolio.yml", "--output", str(portfolio_output)],
    )
    assert portfolio_result.exit_code == 0, portfolio_result.output
    assert json.loads(portfolio_output.read_text(encoding="utf-8"))["workload_count"] == 3

    corpus_result = runner.invoke(
        app,
        ["evaluate-corpus", "--corpus-dir", "examples/corpus", "--output", str(corpus_output)],
    )
    assert corpus_result.exit_code == 0, corpus_result.output
    assert json.loads(corpus_output.read_text(encoding="utf-8"))["decision_accuracy"] == 1.0


def test_cli_case_template_writes_yaml(tmp_path):
    output = tmp_path / "case.yml"
    result = runner.invoke(app, ["case-template", "--case-id", "case-001", "--output", str(output)])
    assert result.exit_code == 0, result.output
    text = output.read_text(encoding="utf-8")
    assert "expert_reviews:" in text
    assert "outcomes:" in text


def test_cli_schema_lists_and_prints_contracts():
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0, result.output
    assert "corpus-case" in result.output
    result = runner.invoke(app, ["schema", "--name", "calibration-report"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["schema_version"] == "1.0"
