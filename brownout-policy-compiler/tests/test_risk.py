from __future__ import annotations

from brownout_policy_compiler.compile_rules import compile_from_paths


def test_action_risk_increases_for_admin_or_vpn_services(compile_options_factory):
    result = compile_from_paths(compile_options_factory())
    vpn_non_priority = [action for action in result.plan.actions if action.service_id == "vpn_access" and action.action_type.value != "PRIORITIZE"]
    assert vpn_non_priority
    assert {action.risk_level.value for action in vpn_non_priority} == {"HIGH"}

