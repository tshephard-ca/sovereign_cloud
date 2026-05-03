from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from .compile_rules import CompileOptions, compile_from_paths
from .data_generator import (
    GENERATED_AT,
    Scenario,
    policy_pack_fixture,
    scenarios,
    service_priority_fixture,
    thresholds_fixture,
    write_endpoint_inventory_csv,
    write_json,
    write_service_priority_questionnaire,
    write_tabletop_worksheet,
    write_yaml,
)
from .decision_package import build_decision_brief, decision_brief_markdown
from .event_schema import load_event
from .models import BrownoutPlan, ServicePriorityFile
from .service_priority import load_service_priority, validate_service_priority


def _write_structured(path: Path, data: dict[str, Any]) -> None:
    suffix = path.suffix.lower()
    if suffix in {".yml", ".yaml"}:
        write_yaml(path, data)
    else:
        write_json(path, data)


def _service_data() -> dict[str, Any]:
    return service_priority_fixture()


def _services(data: dict[str, Any]) -> list[dict[str, Any]]:
    return list(data.get("service_groups", []))


def approval_matrix(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "approval_matrix_version": 1,
        "description": "Synthetic service approval matrix for brownout tabletop and input seeding.",
        "services": [
            {
                "service_id": service["id"],
                "service_display_name": service.get("display_name", service["id"]),
                "priority": service["priority"],
                "approval_required": bool(service.get("approval_required", False)),
                "approver": service.get("approver"),
                "approval_metadata": service.get("approval_metadata", {}),
                "operator_question": "Who can approve temporary restriction for this service during the proposed TTL?",
            }
            for service in _services(data)
        ],
    }


def rollback_controls(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "rollback_controls_version": 1,
        "description": "Synthetic rollback owner and verification controls for service-priority input review.",
        "services": [
            {
                "service_id": service["id"],
                "service_display_name": service.get("display_name", service["id"]),
                "priority": service["priority"],
                "rollback_required": bool(service.get("rollback_required", True)),
                "rollback_owner": service.get("rollback_owner"),
                "rollback_control": service.get("rollback_control", {}),
            }
            for service in _services(data)
        ],
    }


def trusted_sources_profile(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "trusted_sources_version": 1,
        "description": "Synthetic trusted source groups for incident-use review.",
        "trusted_sources": data.get("trusted_sources", {}),
    }


def organization_profile(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "organization_profile_version": 1,
        "description": "Synthetic organization profile fields used to make service-priority decisions reviewable.",
        "organization": data.get("organization", {}),
    }


def write_init_all(output_dir: Path) -> dict[str, str]:
    data = _service_data()
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "service_priority": output_dir / "service_priority.yml",
        "organization": output_dir / "organization.yml",
        "trusted_sources": output_dir / "trusted_sources.yml",
        "endpoint_inventory": output_dir / "endpoint_inventory.csv",
        "approval_matrix": output_dir / "approval_matrix.yml",
        "rollback_controls": output_dir / "rollback_controls.yml",
        "policy_pack": output_dir / "policy_pack.yml",
        "thresholds": output_dir / "thresholds.yml",
        "questionnaire": output_dir / "service_priority_questions.md",
        "tabletop_worksheet": output_dir / "tabletop_worksheet.md",
    }
    write_yaml(paths["service_priority"], data)
    write_yaml(paths["organization"], organization_profile(data))
    write_yaml(paths["trusted_sources"], trusted_sources_profile(data))
    write_endpoint_inventory_csv(paths["endpoint_inventory"], data)
    write_yaml(paths["approval_matrix"], approval_matrix(data))
    write_yaml(paths["rollback_controls"], rollback_controls(data))
    write_yaml(paths["policy_pack"], policy_pack_fixture())
    write_yaml(paths["thresholds"], thresholds_fixture())
    write_service_priority_questionnaire(paths["questionnaire"], data)
    write_tabletop_worksheet(paths["tabletop_worksheet"], scenarios())

    events_dir = output_dir / "events"
    for scenario in scenarios():
        write_json(events_dir / scenario.file_name, scenario.event)
    manifest = {
        "input_seed_bundle_version": 1,
        "generated_at": GENERATED_AT,
        "description": "Deterministic synthetic input data for local brownout policy compiler setup.",
        "files": {name: str(path.relative_to(output_dir)) for name, path in paths.items()},
        "events": [f"events/{scenario.file_name}" for scenario in scenarios()],
    }
    write_json(output_dir / "input_manifest.json", manifest)
    result = {name: str(path) for name, path in paths.items()}
    result["events"] = str(events_dir)
    result["manifest"] = str(output_dir / "input_manifest.json")
    return result


def write_organization_template(output: Path) -> None:
    write_yaml(output, organization_profile(_service_data()))


def write_services_template(output: Path) -> None:
    write_yaml(output, _service_data())


def write_trusted_sources_template(output: Path) -> None:
    write_yaml(output, trusted_sources_profile(_service_data()))


def write_approval_matrix_template(output: Path) -> None:
    write_yaml(output, approval_matrix(_service_data()))


def write_rollback_controls_template(output: Path) -> None:
    write_yaml(output, rollback_controls(_service_data()))


def write_endpoint_inventory_template(output: Path) -> None:
    write_endpoint_inventory_csv(output, _service_data())


def write_policy_pack_template(output: Path) -> None:
    write_yaml(output, policy_pack_fixture())


def write_thresholds_template(output: Path) -> None:
    write_yaml(output, thresholds_fixture())


def write_questionnaire(output: Path) -> None:
    write_service_priority_questionnaire(output, _service_data())


def write_tabletop_template(output: Path) -> None:
    write_tabletop_worksheet(output, scenarios())


def scenario_index() -> dict[str, Scenario]:
    index: dict[str, Scenario] = {}
    for scenario in scenarios():
        stem = Path(scenario.file_name).stem
        aliases = {
            scenario.file_name,
            stem,
            stem.split("_", 1)[-1],
            scenario.incident_id,
            scenario.event["event_id"],
        }
        for alias in aliases:
            index[alias.lower()] = scenario
    return index


def get_scenario(identifier: str) -> Scenario:
    scenario = scenario_index().get(identifier.lower())
    if scenario is None:
        available = ", ".join(sorted({Path(item.file_name).stem for item in scenarios()}))
        raise ValueError(f"unknown scenario {identifier!r}; available scenarios: {available}")
    return scenario


def write_event_scenario(identifier: str, output: Path) -> Scenario:
    scenario = get_scenario(identifier)
    write_json(output, scenario.event)
    return scenario


def list_scenario_metadata() -> dict[str, Any]:
    return {
        "scenario_catalog_version": 1,
        "scenarios": [
            {
                "scenario": Path(scenario.file_name).stem,
                "event_file": scenario.file_name,
                "incident_id": scenario.incident_id,
                "event_id": scenario.event["event_id"],
                "attack_class": scenario.event["attack_class"],
                "severity": scenario.event["severity"],
                "target_count": len(scenario.event.get("targets", [])),
                "description": scenario.description,
            }
            for scenario in scenarios()
        ],
    }


def write_scenario_catalog(output: Path) -> None:
    _write_structured(output, list_scenario_metadata())


def build_readiness_report(services: ServicePriorityFile) -> dict[str, Any]:
    validation = validate_service_priority(services, strict=False, fail_on_p0_shed=True)
    service_items = list(services.service_groups)
    endpoints = [endpoint for service in service_items for endpoint in service.endpoints]
    trusted_source_groups = services.trusted_sources
    priority_counts = Counter(service.priority.value for service in service_items)
    mode_counts = Counter(service.brownout_mode.value for service in service_items)
    action_counts = Counter(action.value for service in service_items for action in service.allowed_actions)
    missing_owner = [service.id for service in service_items if not service.owner]
    missing_approver = [service.id for service in service_items if not service.approver]
    missing_rollback = [
        service.id
        for service in service_items
        if service.rollback_required and (not service.rollback_owner or service.rollback_control is None)
    ]
    missing_trusted_sources = [
        service.id
        for service in service_items
        if service.priority.value in {"P0", "P1"} and not service.trusted_source_groups
    ]
    cannot_degrade_low_priority = [
        service.id
        for service in service_items
        if service.priority.value in {"P3", "P4"}
        and service.brownout_mode.value != "NO_ACTION"
        and not any(action.value in {"SHED_LOW_PRIORITY", "RATE_LIMIT", "DEPRIORITIZE"} for action in service.allowed_actions)
    ]
    shared_endpoint_groups = sorted(
        {endpoint.shared_endpoint_group for endpoint in endpoints if endpoint.shared_endpoint_group}
    )
    checks = {
        "organization_profile_complete": bool(
            services.organization.sector
            and services.organization.operating_model
            and services.organization.regions
            and services.organization.customer_segments
            and services.organization.critical_operating_periods
        ),
        "all_services_have_owner": not missing_owner,
        "all_services_have_approver": not missing_approver,
        "all_services_have_rollback_control": not missing_rollback,
        "p0_p1_have_trusted_sources": not missing_trusted_sources,
        "low_priority_services_can_degrade": not cannot_degrade_low_priority,
        "all_endpoints_have_operational_metadata": all(endpoint.exposure and endpoint.enforcement_points for endpoint in endpoints),
        "trusted_sources_have_review_metadata": all(
            group.review_owner and group.last_reviewed_at and group.review_cadence_days
            for group in trusted_source_groups.values()
        ),
        "traffic_baselines_present": all(service.traffic_baseline is not None for service in service_items),
    }
    score = round((sum(1 for passed in checks.values() if passed) / len(checks)) * 100, 2) if checks else 0
    readiness_gaps = []
    if missing_owner:
        readiness_gaps.append({"code": "SERVICE_OWNER_MISSING", "services": missing_owner})
    if missing_approver:
        readiness_gaps.append({"code": "SERVICE_APPROVER_MISSING", "services": missing_approver})
    if missing_rollback:
        readiness_gaps.append({"code": "ROLLBACK_CONTROL_MISSING", "services": missing_rollback})
    if missing_trusted_sources:
        readiness_gaps.append({"code": "P0_P1_TRUSTED_SOURCE_MISSING", "services": missing_trusted_sources})
    if cannot_degrade_low_priority:
        readiness_gaps.append({"code": "LOW_PRIORITY_DEGRADATION_POLICY_MISSING", "services": cannot_degrade_low_priority})
    if validation.blockers:
        status = "NOT_READY"
    elif score >= 90 and not readiness_gaps:
        status = "READY_FOR_TABLETOP"
    else:
        status = "REVIEW_INPUT_GAPS"
    return {
        "readiness_report_version": 1,
        "review_package_readiness_score": score,
        "status": status,
        "service_groups": len(service_items),
        "trusted_source_groups": len(trusted_source_groups),
        "endpoint_count": len(endpoints),
        "priority_counts": dict(sorted(priority_counts.items())),
        "brownout_mode_counts": dict(sorted(mode_counts.items())),
        "allowed_action_counts": dict(sorted(action_counts.items())),
        "shared_endpoint_groups": shared_endpoint_groups,
        "checks": checks,
        "warnings": validation.warnings,
        "blockers": validation.blockers,
        "readiness_gaps": readiness_gaps,
        "recommended_next_steps": [
            "Confirm P0 and P1 service ownership, approvers, trusted sources, and rollback evidence.",
            "Run a tabletop using representative DDoS mitigation event scenarios before relying on review packages in an incident.",
            "Keep generated review packages as candidates only; no action has been applied by this tool.",
        ],
    }


def write_readiness_from_services(services_path: Path, output: Path) -> dict[str, Any]:
    services = load_service_priority(services_path)
    report = build_readiness_report(services)
    _write_structured(output, report)
    return report


def _tabletop_markdown(result: Any, event_id: str) -> str:
    brief = build_decision_brief(result.plan, result.rollback_plan, result.summary)
    return "# Brownout Tabletop Run\n\n" + decision_brief_markdown(brief).split("\n", 1)[1]


def run_tabletop(
    event_path: Path,
    services_path: Path,
    output_dir: Path,
    config_path: Path | None = None,
    policy_pack_path: Path | None = None,
    incident_id: str | None = None,
    now: str | None = None,
    allow_null_route: bool = False,
    allow_source_blocks: bool = False,
    allow_admin_lockdown: bool = False,
    max_actions: int | None = None,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    event = load_event(event_path)
    result = compile_from_paths(
        CompileOptions(
            event_path=event_path,
            services_path=services_path,
            output_plan=output_dir / "brownout_plan.yml",
            output_actions=output_dir / "actions.csv",
            output_rollback=output_dir / "rollback_plan.yml",
            summary=output_dir / "summary.json",
            config_path=config_path,
            policy_pack_path=policy_pack_path,
            incident_id=incident_id,
            now=now,
            allow_null_route=allow_null_route,
            allow_source_blocks=allow_source_blocks,
            allow_admin_lockdown=allow_admin_lockdown,
            max_actions=max_actions,
        )
    )
    report_path = output_dir / "tabletop_report.md"
    report_path.write_text(_tabletop_markdown(result, event.event_id))
    return {
        "plan": output_dir / "brownout_plan.yml",
        "actions": output_dir / "actions.csv",
        "rollback": output_dir / "rollback_plan.yml",
        "summary": output_dir / "summary.json",
        "decision_brief": output_dir / "decision_brief.json",
        "operator_queue": output_dir / "operator_queue.csv",
        "approval_queue": output_dir / "approval_queue.csv",
        "rollback_clock": output_dir / "rollback_clock.json",
        "blocked_actions": output_dir / "blocked_actions.json",
        "report": report_path,
    }


def _actual_changes(path: Path) -> list[dict[str, Any]]:
    payload = yaml.safe_load(path.read_text()) or {}
    changes = payload.get("actual_changes", [])
    if not isinstance(changes, list):
        raise ValueError("actual_changes must be a list")
    return [item for item in changes if isinstance(item, dict)]


def build_post_incident_diff(plan_path: Path, actual_changes_path: Path) -> dict[str, Any]:
    plan_data = yaml.safe_load(plan_path.read_text()) or {}
    plan = BrownoutPlan.model_validate(plan_data)
    actual_changes = _actual_changes(actual_changes_path)
    actual_by_action_id = {str(change.get("action_id")): change for change in actual_changes if change.get("action_id")}
    intended_action_ids = [action.action_id for action in plan.actions]
    applied = []
    skipped = []
    not_recorded = []
    lacking_rollback_evidence = []
    for action in plan.actions:
        actual = actual_by_action_id.get(action.action_id)
        if actual is None:
            not_recorded.append(
                {
                    "action_id": action.action_id,
                    "service_id": action.service_id,
                    "action_type": action.action_type.value,
                    "risk_level": action.risk_level.value,
                }
            )
            continue
        status = str(actual.get("status", "")).lower()
        entry = {
            "action_id": action.action_id,
            "service_id": action.service_id,
            "action_type": action.action_type.value,
            "risk_level": action.risk_level.value,
            "actual_status": status,
        }
        if status == "applied":
            applied.append(entry)
            if action.action_type.value not in {"MONITOR_ONLY", "NO_ACTION"} and not actual.get("rollback_evidence"):
                lacking_rollback_evidence.append(entry)
        elif status == "skipped":
            entry["reason"] = actual.get("reason", "")
            skipped.append(entry)
        else:
            entry["reason"] = "unrecognized or missing actual status"
            not_recorded.append(entry)
    unknown_actual_changes = [
        change
        for action_id, change in sorted(actual_by_action_id.items())
        if action_id not in intended_action_ids
    ]
    status = "MATCHED_REVIEW_RECORDS"
    if not_recorded or lacking_rollback_evidence or unknown_actual_changes:
        status = "REVIEW_ACTUAL_CHANGES"
    lessons = [
        "Record an actual status for every intended temporary action candidate, including skipped actions.",
        "Capture rollback evidence for each applied temporary policy before closing the incident review.",
    ]
    if skipped:
        lessons.append("Review skipped candidates to tune service-priority policy and approval thresholds.")
    return {
        "post_incident_diff_version": 1,
        "incident_id": plan.incident_id,
        "event_id": plan.event_id,
        "status": status,
        "intended_actions": len(plan.actions),
        "actions_applied": len(applied),
        "actions_skipped": len(skipped),
        "actions_not_recorded": len(not_recorded),
        "actions_lacking_rollback_evidence": len(lacking_rollback_evidence),
        "unknown_actual_changes": unknown_actual_changes,
        "applied": applied,
        "skipped": skipped,
        "not_recorded": not_recorded,
        "lacking_rollback_evidence": lacking_rollback_evidence,
        "lessons_learned": lessons,
    }


def write_post_incident_diff(plan_path: Path, actual_changes_path: Path, output: Path) -> dict[str, Any]:
    diff = build_post_incident_diff(plan_path, actual_changes_path)
    _write_structured(output, diff)
    return diff


def write_services_from_endpoint_inventory(inventory: Path, output: Path) -> dict[str, Any]:
    data = _service_data()
    by_service = {service["id"]: service for service in data["service_groups"]}
    with inventory.open(newline="") as handle:
        for row in csv.DictReader(handle):
            service_id = row.get("service_id")
            if service_id not in by_service:
                continue
            ports = [item for item in (row.get("ports") or "").split(";") if item]
            endpoint = {
                "name": row.get("endpoint_name") or f"{service_id}_endpoint",
                "ip": row.get("ip_or_cidr") or "203.0.113.254",
                "protocol": row.get("protocol") or "tcp",
                "ports": [int(port) if port.isdigit() else port for port in ports],
            }
            by_service[service_id]["endpoints"] = [endpoint]
    write_yaml(output, data)
    return data
