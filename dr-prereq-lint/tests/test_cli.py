import csv
import json

from typer.testing import CliRunner

from dr_prereq_lint.cli import app
from dr_prereq_lint.report import FINDINGS_COLUMNS, OBSERVED_COLUMNS

from conftest import dns_rows, inventory_rows


def test_cli_produces_findings_observed_and_summary(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=False))
    dns = csv_writer(tmp_path / "dns.csv", dns_rows())
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    findings = tmp_path / "findings.csv"
    observed = tmp_path / "observed.csv"
    summary = tmp_path / "summary.json"
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "--backup-inventory",
            str(inv),
            "--dns-log",
            str(dns),
            "--recovery-set",
            "dr-test-001",
            "--resolver-hints",
            str(hints),
            "--output-findings",
            str(findings),
            "--output-observed",
            str(observed),
            "--summary",
            str(summary),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(summary.read_text(encoding="utf-8"))["lint_status"] in {"FAIL", "REVIEW", "PASS"}


def test_findings_csv_has_exact_column_order(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=False))
    dns = csv_writer(tmp_path / "dns.csv", dns_rows())
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    findings = tmp_path / "findings.csv"
    observed = tmp_path / "observed.csv"
    summary = tmp_path / "summary.json"
    CliRunner().invoke(app, ["analyze", "--backup-inventory", str(inv), "--dns-log", str(dns), "--recovery-set", "dr-test-001", "--resolver-hints", str(hints), "--output-findings", str(findings), "--output-observed", str(observed), "--summary", str(summary)])
    with findings.open("r", encoding="utf-8", newline="") as handle:
        assert next(csv.reader(handle)) == FINDINGS_COLUMNS


def test_observed_prereqs_csv_has_exact_column_order(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=False))
    dns = csv_writer(tmp_path / "dns.csv", dns_rows())
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    findings = tmp_path / "findings.csv"
    observed = tmp_path / "observed.csv"
    summary = tmp_path / "summary.json"
    CliRunner().invoke(app, ["analyze", "--backup-inventory", str(inv), "--dns-log", str(dns), "--recovery-set", "dr-test-001", "--resolver-hints", str(hints), "--output-findings", str(findings), "--output-observed", str(observed), "--summary", str(summary)])
    with observed.open("r", encoding="utf-8", newline="") as handle:
        assert next(csv.reader(handle)) == OBSERVED_COLUMNS


def test_summary_json_contains_lint_status(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=False))
    dns = csv_writer(tmp_path / "dns.csv", dns_rows())
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    findings = tmp_path / "findings.csv"
    observed = tmp_path / "observed.csv"
    summary = tmp_path / "summary.json"
    CliRunner().invoke(app, ["analyze", "--backup-inventory", str(inv), "--dns-log", str(dns), "--recovery-set", "dr-test-001", "--resolver-hints", str(hints), "--output-findings", str(findings), "--output-observed", str(observed), "--summary", str(summary)])
    assert "lint_status" in json.loads(summary.read_text(encoding="utf-8"))
