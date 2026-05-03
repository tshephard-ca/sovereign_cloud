import pytest

from dr_prereq_lint.lint_rules import analyze_inputs

from conftest import inventory_rows


def test_pass_when_all_observed_high_confidence_prerequisites_are_present(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dc=True, include_dns=True))
    dns = csv_writer(
        tmp_path / "dns.csv",
        [
            {
                "timestamp": "2026-04-29T08:00:00Z",
                "client_ip": "10.0.1.10",
                "qname": "_ldap._tcp.dc._msdcs.corp.example.internal",
                "qtype": "SRV",
                "answer_names": "dc01.corp.example.internal",
                "answer_ips": "10.0.0.20",
            }
        ],
    )
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    result = analyze_inputs(backup_inventory=inv, dns_log=dns, recovery_set_name="dr-test-001", resolver_hints_path=hints)
    assert result.summary.lint_status == "PASS"


def test_review_when_only_weak_heuristic_findings_exist(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=True))
    dns = csv_writer(tmp_path / "dns.csv", [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "fs.apps.example.internal", "qtype": "A"}])
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    result = analyze_inputs(backup_inventory=inv, dns_log=dns, recovery_set_name="dr-test-001", resolver_hints_path=hints)
    assert result.summary.lint_status == "REVIEW"


def test_fail_when_critical_prerequisite_is_missing(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=True))
    dns = csv_writer(
        tmp_path / "dns.csv",
        [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "_ldap._tcp.dc._msdcs.corp.example.internal", "qtype": "SRV"}],
    )
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    result = analyze_inputs(backup_inventory=inv, dns_log=dns, recovery_set_name="dr-test-001", resolver_hints_path=hints)
    assert result.summary.lint_status == "FAIL"


def test_strict_mode_fails_when_zero_dns_clients_map_to_protected_systems(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=True))
    dns = csv_writer(tmp_path / "dns.csv", [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.9.99", "qname": "sql01.apps.example.internal", "qtype": "A"}])
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    with pytest.raises(ValueError, match="zero DNS clients"):
        analyze_inputs(backup_inventory=inv, dns_log=dns, recovery_set_name="dr-test-001", resolver_hints_path=hints, strict=True)


def test_output_is_deterministic_for_same_inputs(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=True))
    dns = csv_writer(tmp_path / "dns.csv", [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "sql01.apps.example.internal", "qtype": "A"}])
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    first = analyze_inputs(backup_inventory=inv, dns_log=dns, recovery_set_name="dr-test-001", resolver_hints_path=hints)
    second = analyze_inputs(backup_inventory=inv, dns_log=dns, recovery_set_name="dr-test-001", resolver_hints_path=hints)
    assert [f.model_dump() for f in first.findings] == [f.model_dump() for f in second.findings]
