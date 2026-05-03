from dr_prereq_lint.backup_inventory import parse_backup_inventory
from dr_prereq_lint.client_mapping import ClientMapper
from dr_prereq_lint.dns_log import parse_dns_log
from dr_prereq_lint.lint_rules import analyze_inputs

from conftest import dns_rows, inventory_rows


def test_maps_client_ip_to_protected_system(tmp_path, csv_writer):
    inventory = parse_backup_inventory(csv_writer(tmp_path / "inventory.csv", inventory_rows()))
    dns = parse_dns_log(csv_writer(tmp_path / "dns.csv", dns_rows()))
    mapped = ClientMapper(inventory.protected_systems).map_query(dns.rows[0])
    assert mapped.system is not None
    assert mapped.match_basis == "client_ip"


def test_maps_client_name_to_protected_system_fqdn(tmp_path, csv_writer):
    inventory = parse_backup_inventory(csv_writer(tmp_path / "inventory.csv", inventory_rows()))
    dns = parse_dns_log(csv_writer(tmp_path / "dns.csv", dns_rows(client_ip="")))
    mapped = ClientMapper(inventory.protected_systems).map_query(dns.rows[0])
    assert mapped.system is not None
    assert mapped.match_basis == "client_name_fqdn"


def test_ignores_unmapped_clients_by_default(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=True))
    dns = csv_writer(
        tmp_path / "dns.csv",
        [
            {
                "timestamp": "2026-04-29T08:00:00Z",
                "client_ip": "10.0.9.99",
                "client_name": "unmapped.example.internal",
                "qname": "sql01.apps.example.internal",
                "qtype": "A",
                "answer_ips": "10.0.2.30",
                "resolver_name": "dns01.example.internal",
                "resolver_ip": "10.0.0.10",
            }
        ],
    )
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    result = analyze_inputs(backup_inventory=inv, dns_log=dns, recovery_set_name="dr-test-001", resolver_hints_path=hints)
    assert all(obs.category != "database_host" for obs in result.observed)


def test_includes_unmapped_clients_when_flag_is_passed(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=True))
    dns = csv_writer(
        tmp_path / "dns.csv",
        [
            {
                "timestamp": "2026-04-29T08:00:00Z",
                "client_ip": "10.0.9.99",
                "client_name": "unmapped.example.internal",
                "qname": "sql01.apps.example.internal",
                "qtype": "A",
                "answer_ips": "10.0.2.30",
                "resolver_name": "dns01.example.internal",
                "resolver_ip": "10.0.0.10",
            }
        ],
    )
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    result = analyze_inputs(
        backup_inventory=inv,
        dns_log=dns,
        recovery_set_name="dr-test-001",
        resolver_hints_path=hints,
        include_unmapped_clients=True,
    )
    assert any("UNMAPPED_DNS_CLIENT" in obs.reason_codes for obs in result.observed)
