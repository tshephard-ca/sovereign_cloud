from dr_prereq_lint.lint_rules import analyze_inputs

from conftest import inventory_rows


def _run(tmp_path, csv_writer, text_writer, dns_rows, *, include_dc=False, include_dns=True, **kwargs):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dc=include_dc, include_dns=include_dns))
    dns = csv_writer(tmp_path / "dns.csv", dns_rows)
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    return analyze_inputs(backup_inventory=inv, dns_log=dns, recovery_set_name="dr-test-001", resolver_hints_path=hints, **kwargs)


def test_detects_ldap_dc_srv_as_directory_service(tmp_path, csv_writer, text_writer):
    result = _run(
        tmp_path,
        csv_writer,
        text_writer,
        [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "_ldap._tcp.dc._msdcs.corp.example.internal", "qtype": "SRV"}],
    )
    assert any(obs.category == "directory_service" for obs in result.observed)


def test_detects_kerberos_srv_as_kerberos_service(tmp_path, csv_writer, text_writer):
    result = _run(
        tmp_path,
        csv_writer,
        text_writer,
        [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "_kerberos._tcp.corp.example.internal", "qtype": "SRV"}],
    )
    assert any(obs.category == "kerberos_service" for obs in result.observed)


def test_detects_gc_srv_as_global_catalog(tmp_path, csv_writer, text_writer):
    result = _run(
        tmp_path,
        csv_writer,
        text_writer,
        [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "_gc._tcp.corp.example.internal", "qtype": "SRV"}],
    )
    assert any(obs.category == "global_catalog" for obs in result.observed)


def test_detects_internal_database_heuristic_as_medium_confidence(tmp_path, csv_writer, text_writer):
    result = _run(
        tmp_path,
        csv_writer,
        text_writer,
        [
            {"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "sql01.apps.example.internal", "qtype": "A"},
            {"timestamp": "2026-04-29T08:01:00Z", "client_ip": "10.0.1.10", "qname": "sql01.apps.example.internal", "qtype": "A"},
        ],
    )
    obs = next(obs for obs in result.observed if obs.category == "database_host")
    assert obs.confidence == "MEDIUM"


def test_detects_file_share_heuristic_and_marks_review_when_weak(tmp_path, csv_writer, text_writer):
    result = _run(
        tmp_path,
        csv_writer,
        text_writer,
        [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "fs.apps.example.internal", "qtype": "A"}],
    )
    finding = next(f for f in result.findings if f.category == "file_share")
    assert finding.severity == "REVIEW"


def test_ignores_external_qname_by_default(tmp_path, csv_writer, text_writer):
    result = _run(
        tmp_path,
        csv_writer,
        text_writer,
        [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "sql01.external.test", "qtype": "A"}],
    )
    assert all(obs.category != "database_host" for obs in result.observed)


def test_includes_external_qname_when_flag_is_passed(tmp_path, csv_writer, text_writer):
    result = _run(
        tmp_path,
        csv_writer,
        text_writer,
        [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.1.10", "qname": "sql01.external.test", "qtype": "A"}],
        include_external=True,
    )
    obs = next(obs for obs in result.observed if obs.category == "database_host")
    assert "EXTERNAL_QNAME_INCLUDED" in obs.reason_codes
