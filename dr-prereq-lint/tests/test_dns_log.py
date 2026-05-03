import pytest

from dr_prereq_lint.dns_log import filter_dns_window, parse_dns_log


def test_parses_dns_query_csv_with_required_columns(tmp_path, csv_writer):
    path = csv_writer(
        tmp_path / "dns.csv",
        [{"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.0.1", "qname": "SQL01.EXAMPLE.INTERNAL.", "qtype": "a"}],
    )
    result = parse_dns_log(path)
    assert result.rows[0].qname == "sql01.example.internal"
    assert result.rows[0].qtype == "A"


def test_parses_dns_query_csv_with_answer_names_and_ips(tmp_path, csv_writer):
    path = csv_writer(
        tmp_path / "dns.csv",
        [
            {
                "timestamp": "2026-04-29T08:00:00Z",
                "client_ip": "10.0.0.1",
                "qname": "svc.example.internal",
                "qtype": "A",
                "answer_names": "a.example.internal; b.example.internal",
                "answer_ips": "10.0.0.2|10.0.0.3",
            }
        ],
    )
    row = parse_dns_log(path).rows[0]
    assert row.answer_names == ["a.example.internal", "b.example.internal"]
    assert row.answer_ips == ["10.0.0.2", "10.0.0.3"]


def test_filters_dns_rows_to_selected_time_window(tmp_path, csv_writer):
    path = csv_writer(
        tmp_path / "dns.csv",
        [
            {"timestamp": "2026-04-27T08:00:00Z", "client_ip": "10.0.0.1", "qname": "old.example.internal", "qtype": "A"},
            {"timestamp": "2026-04-29T08:00:00Z", "client_ip": "10.0.0.1", "qname": "new.example.internal", "qtype": "A"},
        ],
    )
    rows = parse_dns_log(path).rows
    filtered, warnings = filter_dns_window(rows, 24)
    assert [row.qname for row in filtered] == ["new.example.internal"]
    assert warnings == []


def test_handles_missing_timestamps_in_non_strict_mode(tmp_path, csv_writer):
    path = csv_writer(tmp_path / "dns.csv", [{"client_ip": "10.0.0.1", "qname": "x.example.internal", "qtype": "A"}])
    result = parse_dns_log(path)
    filtered, warnings = filter_dns_window(result.rows, 24)
    assert len(filtered) == 1
    assert "TIMESTAMP_UNPARSEABLE" in result.warnings
    assert "DNS_LOG_WINDOW_ASSUMED" in warnings


def test_strict_mode_fails_when_dns_qname_column_is_missing(tmp_path, csv_writer):
    path = csv_writer(tmp_path / "dns.csv", [{"client_ip": "10.0.0.1", "not_qname": "x"}])
    with pytest.raises(ValueError, match="qname"):
        parse_dns_log(path, strict=True)
