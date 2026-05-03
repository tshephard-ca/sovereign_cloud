import pytest

from dr_prereq_lint.known_prereqs import load_known_prereqs
from dr_prereq_lint.lint_rules import analyze_inputs

from conftest import inventory_rows


def test_detects_answer_names_target_absent_from_recovery_set(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=True))
    dns = csv_writer(
        tmp_path / "dns.csv",
        [
            {
                "timestamp": "2026-04-29T08:00:00Z",
                "client_ip": "10.0.1.10",
                "qname": "_ldap._tcp.dc._msdcs.corp.example.internal",
                "qtype": "SRV",
                "answer_names": "dc01.corp.example.internal",
            }
        ],
    )
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    result = analyze_inputs(backup_inventory=inv, dns_log=dns, recovery_set_name="dr-test-001", resolver_hints_path=hints)
    finding = next(f for f in result.findings if f.category == "directory_service")
    assert finding.finding_code == "SPECIFIC_TARGET_NOT_IN_RECOVERY_SET"


def test_detects_answer_ips_target_present_in_recovery_set(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dc=True, include_dns=True))
    dns = csv_writer(
        tmp_path / "dns.csv",
        [
            {
                "timestamp": "2026-04-29T08:00:00Z",
                "client_ip": "10.0.1.10",
                "qname": "_ldap._tcp.dc._msdcs.corp.example.internal",
                "qtype": "SRV",
                "answer_ips": "10.0.0.20",
            }
        ],
    )
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    result = analyze_inputs(backup_inventory=inv, dns_log=dns, recovery_set_name="dr-test-001", resolver_hints_path=hints)
    finding = next(f for f in result.findings if f.category == "directory_service")
    assert finding.present_in_recovery_set is True
    assert finding.match_basis == "IP_MATCH"


def test_detects_role_level_directory_requirement_without_answer_names(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=True))
    dns = csv_writer(
        tmp_path / "dns.csv",
        [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "_ldap._tcp.dc._msdcs.corp.example.internal", "qtype": "SRV"}],
    )
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    result = analyze_inputs(backup_inventory=inv, dns_log=dns, recovery_set_name="dr-test-001", resolver_hints_path=hints)
    finding = next(f for f in result.findings if f.category == "directory_service")
    assert finding.finding_code == "DIRECTORY_SERVICE_ROLE_NOT_IN_RECOVERY_SET"


def test_satisfies_role_level_directory_requirement_using_role_tags(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dc=True, include_dns=True))
    dns = csv_writer(
        tmp_path / "dns.csv",
        [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "_ldap._tcp.dc._msdcs.corp.example.internal", "qtype": "SRV"}],
    )
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    result = analyze_inputs(backup_inventory=inv, dns_log=dns, recovery_set_name="dr-test-001", resolver_hints_path=hints)
    finding = next(f for f in result.findings if f.category == "directory_service")
    assert finding.present_in_recovery_set is True
    assert finding.match_basis == "ROLE_TAG_MATCH"


def test_known_prereqs_match_is_high_confidence(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=True))
    dns = csv_writer(
        tmp_path / "dns.csv",
        [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "license01.apps.example.internal", "qtype": "A"}],
    )
    known = text_writer(
        tmp_path / "known.yml",
        "internal_domains: [example.internal]\nprerequisites:\n- id: lic\n  display_name: License service\n  category: license_server\n  qname_regex: ['(^|\\.)license[0-9-]*\\.apps\\.example\\.internal$']\n",
    )
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    result = analyze_inputs(
        backup_inventory=inv,
        dns_log=dns,
        recovery_set_name="dr-test-001",
        resolver_hints_path=hints,
        known_prereqs_path=known,
    )
    obs = next(obs for obs in result.observed if obs.category == "license_server")
    assert obs.confidence == "HIGH"
    assert "KNOWN_PREREQ_MATCH" in obs.reason_codes


def test_known_prereqs_invalid_regex_fails_validation(tmp_path, text_writer):
    known = text_writer(
        tmp_path / "known.yml",
        "prerequisites:\n- id: bad\n  category: database_host\n  qname_regex: ['[bad']\n",
    )
    with pytest.raises(ValueError, match="invalid known prerequisite regex"):
        load_known_prereqs(known)
