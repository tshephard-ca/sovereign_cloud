from __future__ import annotations

import pytest

from brownout_policy_compiler.compile_rules import compile_from_paths
from brownout_policy_compiler.config import load_config
from brownout_policy_compiler.event_schema import load_event
from brownout_policy_compiler.models import ActionType, Confidence
from brownout_policy_compiler.normalize import match_event_targets
from brownout_policy_compiler.policy_pack import default_policy_pack
from brownout_policy_compiler.service_priority import load_service_priority

from .conftest import write_json, write_yaml


def test_event_target_matches_service_endpoint_by_ip_protocol_port(examples):
    event = load_event(examples / "events" / "ddos_event.json")
    services = load_service_priority(examples / "service_priority.yml")
    matches, unmatched, result = match_event_targets(event, services)
    assert not result.blockers
    assert not unmatched
    assert {match.service.id for match in matches} == {"vpn_access", "public_marketing_site"}


def test_event_target_with_missing_ports_matches_by_ip_and_lowers_confidence(tmp_path, mutable_event, examples):
    mutable_event["targets"] = [mutable_event["targets"][0]]
    mutable_event["targets"][0].pop("ports")
    event = load_event(write_json(tmp_path / "event.json", mutable_event))
    services = load_service_priority(examples / "service_priority.yml")
    matches, _, result = match_event_targets(event, services)
    assert matches[0].confidence == Confidence.MEDIUM
    assert "EVENT_TARGET_PORTS_MISSING" in matches[0].reason_codes


def test_cidr_endpoint_matching_works(tmp_path, mutable_event, mutable_services):
    mutable_event["targets"] = [mutable_event["targets"][0]]
    mutable_services["service_groups"][-1]["endpoints"][0]["ip"] = "203.0.113.0/24"
    event = load_event(write_json(tmp_path / "event.json", mutable_event))
    services = load_service_priority(write_yaml(tmp_path / "services.yml", mutable_services))
    matches, _, _ = match_event_targets(event, services)
    assert matches[0].service.id == "public_marketing_site"
    assert "CIDR_ENDPOINT_MATCH" in matches[0].reason_codes


def test_multiple_services_matching_same_target_emits_warning(tmp_path, mutable_event, mutable_services):
    duplicate = dict(mutable_services["service_groups"][-1])
    duplicate["id"] = "second_public_web"
    duplicate["priority"] = "P3"
    mutable_services["service_groups"].append(duplicate)
    event = load_event(write_json(tmp_path / "event.json", mutable_event))
    services = load_service_priority(write_yaml(tmp_path / "services.yml", mutable_services))
    _, _, result = match_event_targets(event, services)
    assert "TARGET_MATCHES_MULTIPLE_SERVICES" in result.warnings


def test_unmapped_event_target_warns_non_strict(tmp_path, mutable_event, examples):
    mutable_event["targets"] = [mutable_event["targets"][0]]
    mutable_event["targets"][0]["ip"] = "203.0.113.99"
    event = load_event(write_json(tmp_path / "event.json", mutable_event))
    services = load_service_priority(examples / "service_priority.yml")
    _, unmatched, result = match_event_targets(event, services, strict=False)
    assert unmatched == ["public_web_vip"]
    assert "UNMAPPED_ATTACK_TARGET" in result.warnings
    assert not result.blockers


def test_unmapped_event_target_fails_strict(tmp_path, mutable_event, examples):
    mutable_event["targets"] = [mutable_event["targets"][0]]
    mutable_event["targets"][0]["ip"] = "203.0.113.99"
    event = load_event(write_json(tmp_path / "event.json", mutable_event))
    services = load_service_priority(examples / "service_priority.yml")
    _, _, result = match_event_targets(event, services, strict=True)
    assert "UNMAPPED_ATTACK_TARGET" in result.blockers


def test_p0_service_selects_allow_trusted_and_prioritize(compile_options_factory):
    result = compile_from_paths(compile_options_factory())
    vpn_actions = {action.action_type for action in result.plan.actions if action.service_id == "vpn_access"}
    assert ActionType.ALLOW_TRUSTED_SOURCES in vpn_actions
    assert ActionType.PRIORITIZE in vpn_actions


def test_p0_service_never_selects_shed(compile_options_factory):
    result = compile_from_paths(compile_options_factory())
    p0_actions = [action.action_type for action in result.plan.actions if action.service_priority.value == "P0"]
    assert ActionType.SHED_LOW_PRIORITY not in p0_actions


def test_p1_admin_deny_untrusted_requires_approval(tmp_path, mutable_event, mutable_services, compile_options_factory):
    mutable_event["targets"] = [
        {
            "name": "admin_portal",
            "ip": "203.0.113.50",
            "protocol": "tcp",
            "ports": [443],
            "observed_bps": 100,
            "observed_pps": 100,
            "baseline_bps": 10,
            "baseline_pps": 10,
        }
    ]
    event_path = write_json(tmp_path / "event.json", mutable_event)
    services_path = write_yaml(tmp_path / "services.yml", mutable_services)
    result = compile_from_paths(compile_options_factory(event_path=event_path, services_path=services_path, allow_admin_lockdown=True))
    deny = [action for action in result.plan.actions if action.action_type == ActionType.DENY_UNTRUSTED][0]
    assert deny.approval_required
    assert deny.risk_level.value == "HIGH"


def test_p4_service_selects_shed_low_priority(compile_options_factory):
    result = compile_from_paths(compile_options_factory())
    assert any(action.action_type == ActionType.SHED_LOW_PRIORITY and action.service_id == "public_marketing_site" for action in result.plan.actions)


def test_no_action_service_emits_no_action(tmp_path, mutable_event, mutable_services, compile_options_factory):
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
    mutable_services["service_groups"] = [
        {
            "id": "research_sandbox",
            "display_name": "Research sandbox",
            "priority": "P4",
            "brownout_mode": "NO_ACTION",
            "endpoints": [{"name": "sandbox_vip", "ip": "203.0.113.130", "protocol": "tcp", "ports": [8443]}],
            "allowed_actions": ["MONITOR_ONLY", "NO_ACTION"],
            "rollback_required": True,
        }
    ]
    event_path = write_json(tmp_path / "event.json", mutable_event)
    services_path = write_yaml(tmp_path / "services.yml", mutable_services)
    result = compile_from_paths(compile_options_factory(event_path=event_path, services_path=services_path))
    no_action = [action for action in result.plan.actions if action.action_type == ActionType.NO_ACTION]
    assert len(no_action) == 1
    assert no_action[0].rollback_action_id
    assert result.rollback_plan.rollback_actions == []


def test_application_attack_selects_challenge_when_allowed(compile_options_factory, examples):
    result = compile_from_paths(compile_options_factory(event_path=examples / "events" / "app_layer_event.json"))
    assert any(action.action_type == ActionType.CHALLENGE for action in result.plan.actions)


def test_p1_application_attack_selects_challenge_when_allowed(tmp_path, mutable_event, mutable_services, compile_options_factory):
    mutable_event["attack_class"] = "APPLICATION"
    mutable_event["targets"] = [
        {
            "name": "payment_api",
            "ip": "203.0.113.60",
            "protocol": "tcp",
            "ports": [443],
            "observed_bps": 100,
            "observed_pps": 100,
            "baseline_bps": 10,
            "baseline_pps": 10,
        }
    ]
    for service in mutable_services["service_groups"]:
        if service["id"] == "payment":
            service["allowed_actions"].append("CHALLENGE")
    result = compile_from_paths(
        compile_options_factory(
            event_path=write_json(tmp_path / "event.json", mutable_event),
            services_path=write_yaml(tmp_path / "services.yml", mutable_services),
        )
    )
    assert any(action.action_type == ActionType.CHALLENGE and action.service_priority.value == "P1" for action in result.plan.actions)


def test_volumetric_attack_does_not_source_block_by_default(compile_options_factory):
    result = compile_from_paths(compile_options_factory())
    assert all("SOURCE_BLOCK" not in action.action_type.value for action in result.plan.actions)
    assert "Source-prefix blocking is disabled by default." in result.plan.assumptions


def test_spoofing_likely_disables_source_blocking_even_when_prefixes_exist(compile_options_factory):
    result = compile_from_paths(compile_options_factory(allow_source_blocks=True))
    assert "SPOOFING_LIKELY_SOURCE_BLOCKS_SKIPPED" in result.plan.warnings
    assert all(action.action_type != ActionType.MONITOR_ONLY for action in result.plan.actions)


def test_unmapped_event_target_emits_monitor_only_action(tmp_path, mutable_event, examples, compile_options_factory):
    mutable_event["targets"] = [mutable_event["targets"][0]]
    mutable_event["targets"][0]["ip"] = "203.0.113.99"
    event_path = write_json(tmp_path / "event.json", mutable_event)
    result = compile_from_paths(compile_options_factory(event_path=event_path, services_path=examples / "service_priority.yml"))
    monitor = [action for action in result.plan.actions if action.action_type == ActionType.MONITOR_ONLY]
    assert len(monitor) == 1
    assert monitor[0].service_id == "unmapped_event_target"
    assert "UNMAPPED_ATTACK_TARGET" in monitor[0].reason_codes


def test_source_block_review_is_monitor_only_when_allowed_and_not_spoofed(tmp_path, mutable_event, compile_options_factory):
    mutable_event["signals"]["spoofing_likely"] = False
    event_path = write_json(tmp_path / "event.json", mutable_event)
    result = compile_from_paths(compile_options_factory(event_path=event_path, allow_source_blocks=True))
    monitor = [action for action in result.plan.actions if action.action_type == ActionType.MONITOR_ONLY]
    assert len(monitor) == 1
    assert monitor[0].approval_required
    assert monitor[0].risk_level.value == "HIGH"
    assert monitor[0].parameters["source_block_review_only"] is True


def test_allow_null_route_refuses_p0_or_p1(tmp_path, mutable_event, mutable_services, compile_options_factory):
    mutable_services["service_groups"][1]["allowed_actions"].append("TEMPORARY_NULL_ROUTE")
    mutable_services["service_groups"][1]["brownout_mode"] = "SHED"
    event_path = write_json(tmp_path / "event.json", mutable_event)
    services_path = write_yaml(tmp_path / "services.yml", mutable_services)
    result = compile_from_paths(compile_options_factory(event_path=event_path, services_path=services_path, allow_null_route=True))
    assert "UNSAFE_NULL_ROUTE_REQUESTED" in result.plan.blockers
    assert all(action.action_type != ActionType.TEMPORARY_NULL_ROUTE for action in result.plan.actions)


def test_null_route_requires_allowed_actions_and_short_ttl(tmp_path, mutable_event, mutable_services, compile_options_factory):
    mutable_event["targets"] = [mutable_event["targets"][0]]
    mutable_services["service_groups"] = [mutable_services["service_groups"][-1]]
    mutable_services["service_groups"][0]["allowed_actions"].append("TEMPORARY_NULL_ROUTE")
    mutable_services["service_groups"][0]["max_ttl_minutes"] = 10
    event_path = write_json(tmp_path / "event.json", mutable_event)
    services_path = write_yaml(tmp_path / "services.yml", mutable_services)
    result = compile_from_paths(compile_options_factory(event_path=event_path, services_path=services_path, allow_null_route=True))
    null_actions = [action for action in result.plan.actions if action.action_type == ActionType.TEMPORARY_NULL_ROUTE]
    assert null_actions
    assert null_actions[0].ttl_minutes <= load_config().null_route_max_ttl_minutes


def test_action_count_respects_max_actions(compile_options_factory):
    result = compile_from_paths(compile_options_factory(max_actions=2))
    assert result.plan.action_count == 2
    assert "ACTION_LIMIT_REACHED" in result.plan.warnings


def test_output_is_deterministic_for_same_inputs(compile_options_factory):
    first = compile_from_paths(compile_options_factory())
    second = compile_from_paths(compile_options_factory())
    assert first.plan.model_dump(mode="json") == second.plan.model_dump(mode="json")
