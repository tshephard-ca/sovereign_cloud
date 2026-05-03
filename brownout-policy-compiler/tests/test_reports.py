from __future__ import annotations

import json

import yaml

from brownout_policy_compiler.compile_rules import compile_from_paths
from brownout_policy_compiler.report import write_markdown_summary


def test_brownout_plan_has_review_only_mode(compile_options_factory):
    compile_from_paths(compile_options_factory())
    plan = yaml.safe_load(compile_options_factory().output_plan.read_text())
    assert plan["mode"] == "REVIEW_ONLY"


def test_summary_json_includes_lint_status_and_action_counts(compile_options_factory):
    result = compile_from_paths(compile_options_factory())
    summary = json.loads(compile_options_factory().summary.read_text())
    assert summary["lint_status"] == result.summary.lint_status
    assert summary["actions"]["total"] == len(result.plan.actions)


def test_informational_review_only_warning_does_not_prevent_pass(tmp_path, mutable_event, mutable_services, compile_options_factory):
    mutable_event["targets"] = [
        {
            "name": "sandbox_vip",
            "ip": "203.0.113.130",
            "protocol": "tcp",
            "ports": [8443],
            "observed_bps": 100,
            "observed_pps": 100,
            "baseline_bps": 10,
            "baseline_pps": 10,
        }
    ]
    mutable_event["signals"] = {"protocol_mix": {"http_get": 100}, "spoofing_likely": False}
    mutable_services["organization"].update(
        {
            "sector": "test operations",
            "operating_model": "centralized",
            "regions": ["region-a"],
            "customer_segments": ["internal"],
            "critical_operating_periods": [{"name": "test_window"}],
        }
    )
    mutable_services["trusted_sources"] = {}
    mutable_services["service_groups"] = [
        {
            "id": "research_sandbox",
            "display_name": "Research sandbox",
            "priority": "P4",
            "brownout_mode": "NO_ACTION",
            "business_process": "non-production experimentation",
            "owner": "application operations",
            "approver": "incident commander",
            "rollback_owner": "application operations",
            "criticality_rationale": "non-production service",
            "rto_minutes": 120,
            "rpo_minutes": 60,
            "slo": "best effort",
            "user_population": "internal test users",
            "revenue_impact": "none",
            "public_safety_impact": "none",
            "customer_tiers": ["internal"],
            "contractual_obligations": ["none"],
            "regulated_workflows": [],
            "approval_metadata": {
                "named_approver": "incident commander",
                "role_group": "incident command",
                "approval_channel": "incident bridge",
                "approval_expiry_minutes": 10,
                "emergency_delegation": "deputy incident commander",
            },
            "rollback_control": {
                "rollback_owner": "application operations",
                "verification_steps": ["Confirm no temporary policy was applied."],
            },
            "traffic_baseline": {"baseline_bps": 10, "baseline_pps": 10},
            "endpoints": [{"name": "sandbox_vip", "ip": "203.0.113.130", "protocol": "tcp", "ports": [8443], "exposure": "PRIVATE", "enforcement_points": ["LOAD_BALANCER"]}],
            "allowed_actions": ["NO_ACTION"],
            "rollback_required": True,
        }
    ]
    from .conftest import write_json, write_yaml

    result = compile_from_paths(
        compile_options_factory(
            event_path=write_json(tmp_path / "event.json", mutable_event),
            services_path=write_yaml(tmp_path / "services.yml", mutable_services),
        )
    )
    assert result.summary.lint_status == "PASS"
    assert "REVIEW_ONLY_OUTPUT" in result.plan.warnings


def test_explain_writes_markdown_summary(tmp_path, compile_options_factory):
    compile_from_paths(compile_options_factory())
    markdown = tmp_path / "summary.md"
    write_markdown_summary(compile_options_factory().output_plan, markdown)
    text = markdown.read_text()
    assert "Brownout Decision Brief" in text
    assert "Protect Now" in text
    assert "Degrade Candidates" in text
    assert "Actions" in text
