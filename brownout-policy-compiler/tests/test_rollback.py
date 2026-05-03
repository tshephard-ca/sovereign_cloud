from __future__ import annotations

from brownout_policy_compiler.compile_rules import compile_from_paths


def test_every_generated_action_has_ttl(compile_options_factory):
    result = compile_from_paths(compile_options_factory())
    assert all(action.ttl_minutes > 0 for action in result.plan.actions)


def test_every_generated_action_has_rollback_action_id(compile_options_factory):
    result = compile_from_paths(compile_options_factory())
    assert all(action.rollback_action_id for action in result.plan.actions)


def test_rollback_plan_includes_one_entry_per_action(compile_options_factory):
    result = compile_from_paths(compile_options_factory())
    rollback_required = [action for action in result.plan.actions if action.action_type.value not in {"MONITOR_ONLY", "NO_ACTION"}]
    assert len(result.rollback_plan.rollback_actions) == len(rollback_required)


def test_rollback_order_is_inverse_of_action_order(compile_options_factory):
    result = compile_from_paths(compile_options_factory())
    action_ids = [action.action_id for action in result.plan.actions if action.action_type.value not in {"MONITOR_ONLY", "NO_ACTION"}]
    rollback_action_ids = [action.action_id for action in result.rollback_plan.rollback_actions]
    assert rollback_action_ids == list(reversed(action_ids))
