import csv
import json
import zipfile

from typer.testing import CliRunner

from dr_prereq_lint.answer_map import enrich_dns_rows_with_answer_map, load_answer_map
from dr_prereq_lint.cli import app
from dr_prereq_lint.dns_log import parse_dns_log
from dr_prereq_lint.generate_data import generate_benchmark_data
from dr_prereq_lint.human_reports import write_checklist
from dr_prereq_lint.lint_rules import analyze_inputs
from dr_prereq_lint.models import ObservedPrerequisite
from dr_prereq_lint.schemas import schema_catalog

from conftest import inventory_rows


def test_schema_catalog_includes_core_contracts():
    catalog = schema_catalog()
    assert "backup_inventory" in catalog["inputs"]
    assert "findings_csv" in catalog["outputs"]
    assert "DNS_RESOLVER_NOT_IN_RECOVERY_SET" in catalog["reason_codes"]


def test_answer_map_enriches_dns_rows(tmp_path, csv_writer):
    dns = csv_writer(
        tmp_path / "dns.csv",
        [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "sql01.apps.example.internal", "qtype": "A"}],
    )
    answer_map = csv_writer(
        tmp_path / "answer_map.csv",
        [{"qname": "sql01.apps.example.internal", "qtype": "A", "answer_names": "sql01.apps.example.internal", "answer_ips": "10.0.2.30", "source": "offline", "observed_utc": "2026-04-29T08:00:00Z"}],
    )
    rows = parse_dns_log(dns).rows
    enriched, count = enrich_dns_rows_with_answer_map(rows, load_answer_map(answer_map))
    assert count == 1
    assert enriched[0].answer_ips == ["10.0.2.30"]


def test_analyze_summary_includes_evidence_quality_and_metadata(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=True))
    dns = csv_writer(
        tmp_path / "dns.csv",
        [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "sql01.apps.example.internal", "qtype": "A"}],
    )
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    result = analyze_inputs(backup_inventory=inv, dns_log=dns, recovery_set_name="dr-test-001", resolver_hints_path=hints)
    assert result.summary.schema_version == "1.0"
    assert result.summary.evidence_quality["status"] in {"GOOD", "PARTIAL", "WEAK"}
    assert str(inv) in result.summary.run_metadata["input_fingerprints"]


def test_cli_generates_sample_data_and_expected_outputs(tmp_path):
    result = CliRunner().invoke(app, ["generate-sample-data", "--scenario", "missing-database-host", "--output-dir", str(tmp_path / "sample")])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "sample" / "backup_inventory.csv").exists()
    assert json.loads((tmp_path / "sample" / "expected_summary.json").read_text(encoding="utf-8"))["lint_status"] in {"FAIL", "REVIEW", "PASS"}


def test_cli_init_inputs_creates_templates(tmp_path):
    result = CliRunner().invoke(app, ["init-inputs", "--output-dir", str(tmp_path / "inputs")])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "inputs" / "backup_inventory_template.csv").exists()
    assert (tmp_path / "inputs" / "offline_answer_map_template.csv").exists()


def test_cli_validation_explain_writes_report(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=True))
    dns = csv_writer(tmp_path / "dns.csv", [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "sql01.apps.example.internal", "qtype": "A"}])
    report = tmp_path / "validation.json"
    result = CliRunner().invoke(app, ["validate-inputs", "--backup-inventory", str(inv), "--dns-log", str(dns), "--validation-report", str(report)])
    assert result.exit_code == 0, result.output
    assert json.loads(report.read_text(encoding="utf-8"))["valid"] is True


def test_cli_report_questions_checklist_and_bundle(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=False))
    dns = csv_writer(tmp_path / "dns.csv", [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "sql01.apps.example.internal", "qtype": "A"}])
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    findings = tmp_path / "findings.csv"
    observed = tmp_path / "observed.csv"
    summary = tmp_path / "summary.json"
    analyze = CliRunner().invoke(app, ["analyze", "--backup-inventory", str(inv), "--dns-log", str(dns), "--recovery-set", "dr-test-001", "--resolver-hints", str(hints), "--output-findings", str(findings), "--output-observed", str(observed), "--summary", str(summary), "--compare-window-hours", "24", "--compare-window-hours", "168"])
    assert analyze.exit_code == 0, analyze.output
    assert json.loads(summary.read_text(encoding="utf-8"))["window_comparison"]
    report = tmp_path / "report.md"
    questions = tmp_path / "questions.md"
    checklist = tmp_path / "checklist.csv"
    bundle = tmp_path / "bundle.zip"
    assert CliRunner().invoke(app, ["report", "--findings", str(findings), "--summary", str(summary), "--output", str(report)]).exit_code == 0
    assert CliRunner().invoke(app, ["generate-questions", "--findings", str(findings), "--output", str(questions)]).exit_code == 0
    assert CliRunner().invoke(app, ["checklist", "--observed", str(observed), "--output", str(checklist)]).exit_code == 0
    assert CliRunner().invoke(app, ["bundle-evidence", "--findings", str(findings), "--observed", str(observed), "--summary", str(summary), "--output", str(bundle), "--redact", "--input-file", str(inv)]).exit_code == 0
    with checklist.open("r", encoding="utf-8", newline="") as handle:
        assert next(csv.reader(handle)) == ["category", "prerequisite", "status", "evidence", "owner", "decision", "notes"]
    with zipfile.ZipFile(bundle) as archive:
        assert "handoff_questions.md" in archive.namelist()


def test_benchmark_generator_covers_realistic_input_gaps(tmp_path):
    out = tmp_path / "benchmark"
    generate_benchmark_data(out, protected_systems=100, queries=2000, missing_prereq_rate=0.5, seed=11)
    inventory = list(csv.DictReader((out / "backup_inventory.csv").open(encoding="utf-8")))
    dns = list(csv.DictReader((out / "dns_queries.csv").open(encoding="utf-8")))
    assert sum(row["protected"] == "true" for row in inventory) == 100
    assert all(row["os"] and row["backup_job"] and row["last_success_utc"] and row["application_owner"] for row in inventory)
    assert any(";" in row["ip_addresses"] for row in inventory)
    assert any("fd00::" in row["ip_addresses"] for row in inventory)
    assert any(row["aliases"] for row in inventory)
    assert len({row["owner_team"] for row in inventory}) >= 5
    assert len({row["qname"] for row in dns if row["qname"]}) >= 100
    assert any(not row["client_ip"] and row["client_name"] for row in dns)
    assert any(row["client_ip"] and not row["client_name"] for row in dns)
    assert any(row["client_ip"] == "10.1.250.20" for row in dns)
    assert any(not row["resolver_name"] and not row["resolver_ip"] for row in dns)
    assert any(not row["qname"] for row in dns)
    assert any(row["client_ip"] == "not_an_ip" for row in dns)
    assert {"CNAME", "TXT", "MX", "NS", "SOA", "HTTPS"}.issubset({row["qtype"] for row in dns})
    assert all(row["query_id"] and row["protocol"] and row["view"] and row["ttl"] and row["raw_line"] for row in dns)
    assert any(row["qtype"] == "UNSUPPORTED" for row in dns)
    assert any("999.999.999.999" in row["answer_ips"] for row in dns)
    assert (out / "answer_map.csv").exists()
    assert (out / "accepted_risks.yml").exists()
    assert (out / "owner_map.csv").exists()
    assert (out / "recovery_sets.yml").exists()
    assert (out / "dns_queries_malformed.csv").exists()
    accuracy = json.loads((out / "accuracy_report.json").read_text(encoding="utf-8"))
    assert accuracy["accuracy_status"] == "PASS"
    assert accuracy["unexpected_missing_candidates"] == []


def test_support_files_are_consumed_in_outputs(tmp_path):
    out = tmp_path / "benchmark"
    generate_benchmark_data(out, protected_systems=80, queries=1500, missing_prereq_rate=0.5, seed=12)
    findings = tmp_path / "findings.csv"
    observed = tmp_path / "observed.csv"
    summary = tmp_path / "summary.json"
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "--backup-inventory", str(out / "backup_inventory.csv"),
            "--dns-log", str(out / "dns_queries.csv"),
            "--known-prereqs", str(out / "known_prereqs.yml"),
            "--resolver-hints", str(out / "resolver_hints.yml"),
            "--answer-map", str(out / "answer_map.csv"),
            "--accepted-risks", str(out / "accepted_risks.yml"),
            "--recovery-sets", str(out / "recovery_sets.yml"),
            "--recovery-set", "dr-test-001",
            "--include-unmapped-clients",
            "--include-external",
            "--output-findings", str(findings),
            "--output-observed", str(observed),
            "--summary", str(summary),
        ],
    )
    assert result.exit_code == 0, result.output
    summary_payload = json.loads(summary.read_text(encoding="utf-8"))
    assert summary_payload["run_metadata"]["accepted_risk_count"] >= 1
    assert summary_payload["run_metadata"]["recovery_set_metadata"]["name"] == "dr-test-001"
    assert summary_payload["run_metadata"]["business_context"]["protected_systems_by_owner_team"]
    assert summary_payload["evidence_quality"]["input_audit"]["duplicate_fqdn_count"] >= 1
    finding_rows = list(csv.DictReader(findings.open(encoding="utf-8")))
    assert any(row["finding_code"] == "ACCEPTED_RISK_APPLIED" for row in finding_rows)

    report = tmp_path / "report.md"
    questions = tmp_path / "questions.md"
    checklist = tmp_path / "checklist.csv"
    assert CliRunner().invoke(app, ["report", "--findings", str(findings), "--summary", str(summary), "--owner-map", str(out / "owner_map.csv"), "--output", str(report)]).exit_code == 0
    assert "## Business Context" in report.read_text(encoding="utf-8")
    assert CliRunner().invoke(app, ["generate-questions", "--findings", str(findings), "--owner-map", str(out / "owner_map.csv"), "--output", str(questions)]).exit_code == 0
    assert "time source" not in questions.read_text(encoding="utf-8").lower()
    assert CliRunner().invoke(app, ["checklist", "--observed", str(observed), "--owner-map", str(out / "owner_map.csv"), "--output", str(checklist)]).exit_code == 0
    checklist_rows = list(csv.DictReader(checklist.open(encoding="utf-8")))
    assert any(row["owner"] for row in checklist_rows)
    assert any(row["status"] == "absent_from_recovery_set" for row in checklist_rows)


def test_benchmark_outcome_profiles_cover_pass_review_fail(tmp_path):
    statuses = {}
    for profile in ["pass", "review", "fail"]:
        out = tmp_path / profile
        generate_benchmark_data(out, protected_systems=80, queries=1500, missing_prereq_rate=0.5, seed=21, outcome_profile=profile)
        statuses[profile] = json.loads((out / "expected_summary.json").read_text(encoding="utf-8"))["lint_status"]
    assert statuses == {"pass": "PASS", "review": "REVIEW", "fail": "FAIL"}


def test_compare_recovery_sets_command_writes_json(tmp_path):
    out = tmp_path / "benchmark"
    generate_benchmark_data(out, protected_systems=80, queries=1200, missing_prereq_rate=0.5, seed=13)
    comparison = tmp_path / "comparison.json"
    result = CliRunner().invoke(
        app,
        [
            "compare-recovery-sets",
            "--backup-inventory", str(out / "backup_inventory.csv"),
            "--dns-log", str(out / "dns_queries.csv"),
            "--known-prereqs", str(out / "known_prereqs.yml"),
            "--resolver-hints", str(out / "resolver_hints.yml"),
            "--answer-map", str(out / "answer_map.csv"),
            "--recovery-sets", str(out / "recovery_sets.yml"),
            "--include-unmapped-clients",
            "--output", str(comparison),
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(comparison.read_text(encoding="utf-8"))
    assert {item["recovery_set"] for item in payload["recovery_sets"]} >= {"dr-test-001", "shared-services"}


def test_equivalent_target_findings_are_deduplicated(tmp_path, csv_writer, text_writer):
    inventory = csv_writer(
        tmp_path / "inventory.csv",
        [
            {"workload_name": "app01", "fqdn": "app01.apps.example.internal", "ip_addresses": "10.0.1.10", "protected": "true", "recovery_set": "dr-test-001", "include_in_recovery_set": "true", "aliases": "", "role_tags": "application"},
            {"workload_name": "app02", "fqdn": "app02.apps.example.internal", "ip_addresses": "10.0.1.11", "protected": "true", "recovery_set": "dr-test-001", "include_in_recovery_set": "true", "aliases": "", "role_tags": "application"},
            {"workload_name": "files01", "fqdn": "files01.apps.example.internal", "ip_addresses": "10.0.3.40", "protected": "true", "recovery_set": "shared-services", "include_in_recovery_set": "false", "aliases": "", "role_tags": "file_server"},
            {"workload_name": "dns01", "fqdn": "dns01.example.internal", "ip_addresses": "10.0.0.10", "protected": "true", "recovery_set": "dr-test-001", "include_in_recovery_set": "true", "aliases": "", "role_tags": "dns_resolver"},
        ],
    )
    dns = csv_writer(
        tmp_path / "dns.csv",
        [
            {"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "files01.apps.example.internal", "qtype": "A", "answer_names": "", "answer_ips": "10.0.3.40", "resolver_name": "dns01.example.internal", "resolver_ip": "10.0.0.10"},
            {"timestamp": "2026-04-29T08:01:00Z", "client_ip": "10.0.1.10", "qname": "_cifs._tcp.apps.example.internal", "qtype": "SRV", "answer_names": "files01.apps.example.internal", "answer_ips": "10.0.3.40", "resolver_name": "dns01.example.internal", "resolver_ip": "10.0.0.10"},
            {"timestamp": "2026-04-29T08:02:00Z", "client_ip": "10.0.1.10", "qname": "files01.apps.example.internal", "qtype": "A", "answer_names": "", "answer_ips": "10.0.3.40", "resolver_name": "dns01.example.internal", "resolver_ip": "10.0.0.10"},
            {"timestamp": "2026-04-29T08:03:00Z", "client_ip": "10.0.1.11", "qname": "_cifs._tcp.apps.example.internal", "qtype": "SRV", "answer_names": "files01.apps.example.internal", "answer_ips": "10.0.3.40", "resolver_name": "dns01.example.internal", "resolver_ip": "10.0.0.10"},
            {"timestamp": "2026-04-29T08:04:00Z", "client_ip": "10.0.1.11", "qname": "files01.apps.example.internal", "qtype": "A", "answer_names": "", "answer_ips": "10.0.3.40", "resolver_name": "dns01.example.internal", "resolver_ip": "10.0.0.10"},
        ],
    )
    known = text_writer(tmp_path / "known.yml", "internal_domains: [example.internal]\nprerequisites:\n- id: files\n  display_name: File services\n  category: file_share\n  qname_regex: ['(^|\\.)files?[0-9-]*\\.apps\\.example\\.internal$']\n")
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    result = analyze_inputs(backup_inventory=inventory, dns_log=dns, recovery_set_name="dr-test-001", known_prereqs_path=known, resolver_hints_path=hints)
    missing_file_findings = [finding for finding in result.findings if finding.category == "file_share" and not finding.present_in_recovery_set]
    assert len(missing_file_findings) == 1
    assert missing_file_findings[0].observed_query_count == 5
    assert missing_file_findings[0].severity == "CRITICAL"


def test_non_required_known_prereq_is_informational(tmp_path, csv_writer, text_writer):
    inventory = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=True))
    dns = csv_writer(tmp_path / "dns.csv", [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "ntp01.example.internal", "qtype": "A", "answer_ips": "10.0.0.12", "resolver_name": "dns01.example.internal", "resolver_ip": "10.0.0.10"}])
    known = text_writer(tmp_path / "known.yml", "internal_domains: [example.internal]\nprerequisites:\n- id: time\n  display_name: Time service\n  category: time_service\n  qname_regex: ['(^|\\.)ntp[0-9-]*\\.example\\.internal$']\n  required_in_recovery_set: false\n")
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    result = analyze_inputs(backup_inventory=inventory, dns_log=dns, recovery_set_name="dr-test-001", known_prereqs_path=known, resolver_hints_path=hints)
    finding = next(finding for finding in result.findings if finding.category == "time_service")
    assert finding.severity == "INFO"
    assert finding.finding_code == "OPTIONAL_PREREQ_OBSERVED"
    assert result.summary.lint_status == "PASS"
    observed = next(item for item in result.observed if item.category == "time_service")
    assert "OPTIONAL_PREREQ_OBSERVED" in observed.reason_codes
    checklist = tmp_path / "checklist.csv"
    write_checklist(checklist, result.observed)
    rows = list(csv.DictReader(checklist.open(encoding="utf-8")))
    assert next(row for row in rows if row["category"] == "time_service")["status"] == "optional"


def test_window_comparison_includes_diffs(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=True))
    dns = csv_writer(
        tmp_path / "dns.csv",
        [
            {"timestamp": "2026-04-20T08:00:00Z", "client_ip": "10.0.1.10", "qname": "sql01.apps.example.internal", "qtype": "A"},
            {"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "fs.apps.example.internal", "qtype": "A"},
        ],
    )
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    findings = tmp_path / "findings.csv"
    observed = tmp_path / "observed.csv"
    summary = tmp_path / "summary.json"
    result = CliRunner().invoke(app, ["analyze", "--backup-inventory", str(inv), "--dns-log", str(dns), "--recovery-set", "dr-test-001", "--resolver-hints", str(hints), "--compare-window-hours", "24", "--compare-window-hours", "720", "--output-findings", str(findings), "--output-observed", str(observed), "--summary", str(summary)])
    assert result.exit_code == 0, result.output
    comparison = json.loads(summary.read_text(encoding="utf-8"))["window_comparison"]
    assert "new_missing_prerequisites" in comparison[0]
    assert "persisting_missing_prerequisites" in comparison[1]


def test_checklist_marks_optional_rows(tmp_path):
    observed = [
        ObservedPrerequisite(category="time_service", prerequisite_name="Time service", confidence="HIGH", present_in_recovery_set=False, reason_codes=["OPTIONAL_PREREQ_OBSERVED"]),
    ]
    output = tmp_path / "checklist.csv"
    write_checklist(output, observed)
    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert rows[0]["status"] == "optional"
