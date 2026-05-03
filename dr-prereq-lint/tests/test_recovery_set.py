from dr_prereq_lint.lint_rules import analyze_inputs

from conftest import dns_rows, inventory_rows


def test_emits_dns_resolver_not_in_recovery_set_from_resolver_hints(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=False))
    dns = csv_writer(tmp_path / "dns.csv", dns_rows())
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    result = analyze_inputs(backup_inventory=inv, dns_log=dns, recovery_set_name="dr-test-001", resolver_hints_path=hints)
    assert any(f.finding_code == "DNS_RESOLVER_NOT_IN_RECOVERY_SET" for f in result.findings)


def test_emits_dns_resolver_identity_unknown_when_absent(tmp_path, csv_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=True))
    dns = csv_writer(
        tmp_path / "dns.csv",
        [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "sql01.apps.example.internal", "qtype": "A"}],
    )
    result = analyze_inputs(backup_inventory=inv, dns_log=dns, recovery_set_name="dr-test-001")
    assert "DNS_RESOLVER_IDENTITY_UNKNOWN" in result.summary.warnings
