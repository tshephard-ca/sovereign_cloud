from __future__ import annotations

import csv
import json

from brownout_policy_compiler.compile_rules import compile_from_paths


def test_redaction_preserves_priorities_ports_action_types_reason_codes_and_ttls(compile_options_factory):
    result = compile_from_paths(compile_options_factory(redact=True))
    with open(compile_options_factory().output_actions, newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert {row["service_priority"] for row in rows} == {action.service_priority.value for action in result.plan.actions}
    assert {row["action_type"] for row in rows} == {action.action_type.value for action in result.plan.actions}
    assert all(row["ttl_minutes"] for row in rows)
    assert all(row["reason_codes"] for row in rows)
    assert any("500" in row["ports"] or "80" in row["ports"] for row in rows)


def test_redaction_removes_emails_and_hashes_public_ips(compile_options_factory):
    compile_from_paths(compile_options_factory(redact=True))
    summary_text = compile_options_factory().summary.read_text()
    plan_text = compile_options_factory().output_plan.read_text()
    assert "@example.invalid" not in summary_text
    assert "203.0.113." not in plan_text
    assert "public_ip_hash_" in plan_text
    assert "198.51.100.0/24" not in plan_text
    assert "cidr_hash_" in plan_text


def test_redaction_covers_decision_package_and_embedded_service_names(compile_options_factory):
    compile_from_paths(compile_options_factory(redact=True))
    options = compile_options_factory()
    decision_markdown = options.summary.with_name("decision_brief.md").read_text()
    operator_queue = options.summary.with_name("operator_queue.csv").read_text()
    rollback_clock = options.summary.with_name("rollback_clock.json").read_text()
    decision_json = json.loads(options.summary.with_name("decision_brief.json").read_text())
    assert "VPN access" not in decision_markdown
    assert "Public marketing site" not in decision_markdown
    assert "vpn_access" not in operator_queue
    assert "public_marketing_site" not in operator_queue
    assert "vpn_access" not in rollback_clock
    assert "public_marketing_site" not in rollback_clock
    assert "service_" in decision_markdown
    assert "service_" in operator_queue
    assert decision_json["protect_now"][0]["service_display_name"].startswith("service_")
    assert all(service_id.startswith("service_") for service_id in decision_json["rollback_clock"]["rollback_actions_by_service"])
