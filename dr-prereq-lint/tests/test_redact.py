from dr_prereq_lint.lint_rules import analyze_inputs
from dr_prereq_lint.redact import redact_outputs

from conftest import dns_rows, inventory_rows


def test_redaction_preserves_counts_and_reason_codes(tmp_path, csv_writer, text_writer):
    inv = csv_writer(tmp_path / "inventory.csv", inventory_rows(include_dns=False))
    dns = csv_writer(tmp_path / "dns.csv", dns_rows())
    hints = text_writer(tmp_path / "resolver.yml", "resolvers:\n- name: dns01.example.internal\n  ip_addresses: [10.0.0.10]\n")
    result = analyze_inputs(backup_inventory=inv, dns_log=dns, recovery_set_name="dr-test-001", resolver_hints_path=hints)
    findings, observed, summary = redact_outputs(result.findings, result.observed, result.summary)
    assert findings[0].observed_query_count == result.findings[0].observed_query_count
    assert findings[0].reason_codes == result.findings[0].reason_codes
    assert summary.findings == result.summary.findings
