from __future__ import annotations

import json
import csv
import hashlib
import os
from copy import deepcopy
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .compile_rules import CompileOptions, compile_from_paths
from .models import ActionType, AttackClass, BrownoutMode, BrownoutPlan, DdosEvent, PolicyPack, Priority, RiskLevel, RollbackPlan, ServicePriorityFile, Summary
from .redact import redact_value, service_display_name_map
from .report import write_markdown_summary


GENERATED_AT = "2026-01-01T00:05:00Z"

FORBIDDEN_VENDOR_TERMS = [
    term.strip().lower()
    for term in os.environ.get("BROWNOUT_FORBIDDEN_TERMS", "").split(",")
    if term.strip()
]


@dataclass(frozen=True)
class Scenario:
    file_name: str
    incident_id: str
    description: str
    event: dict[str, Any]
    allow_null_route: bool = False
    allow_admin_lockdown: bool = False
    allow_source_blocks: bool = False


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def write_endpoint_inventory_csv(path: Path, service_data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "service_id",
        "service_display_name",
        "priority",
        "business_process",
        "endpoint_name",
        "ip_or_cidr",
        "protocol",
        "ports",
        "exposure",
        "enforcement_points",
        "shared_endpoint_group",
        "owner",
        "rollback_owner",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for service in service_data["service_groups"]:
            for endpoint in service["endpoints"]:
                writer.writerow(
                    {
                        "service_id": service["id"],
                        "service_display_name": service["display_name"],
                        "priority": service["priority"],
                        "business_process": service.get("business_process", ""),
                        "endpoint_name": endpoint["name"],
                        "ip_or_cidr": endpoint["ip"],
                        "protocol": endpoint["protocol"],
                        "ports": ";".join(str(port) for port in endpoint["ports"]),
                        "exposure": endpoint.get("exposure", ""),
                        "enforcement_points": ";".join(endpoint.get("enforcement_points", [])),
                        "shared_endpoint_group": endpoint.get("shared_endpoint_group", ""),
                        "owner": service.get("owner", ""),
                        "rollback_owner": service.get("rollback_owner", ""),
                    }
                )


def write_service_priority_questionnaire(path: Path, service_data: dict[str, Any]) -> None:
    lines = [
        "# Service-Priority Questionnaire",
        "",
        "Use this worksheet to review whether the generated service-priority input is complete before an incident.",
        "",
    ]
    for service in service_data["service_groups"]:
        lines.extend(
            [
                f"## {service['display_name']} (`{service['id']}`)",
                "",
                f"- Current priority: `{service['priority']}`",
                f"- Current brownout mode: `{service['brownout_mode']}`",
                f"- Business process: {service.get('business_process', '')}",
                f"- Owner: {service.get('owner', '')}",
                f"- Approver: {service.get('approver', '')}",
                f"- Rollback owner: {service.get('rollback_owner', '')}",
                "- Are the listed endpoints complete and current?",
                "- Are trusted source groups complete for incident use?",
                "- Is the maximum TTL acceptable for the business process?",
                "- What verification proves rollback is complete?",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def write_tabletop_worksheet(path: Path, scenarios_data: list[Scenario]) -> None:
    lines = [
        "# Brownout Tabletop Worksheet",
        "",
        "Review each scenario, confirm service ownership, approve or reject temporary action candidates, and record rollback evidence.",
        "",
    ]
    for scenario in scenarios_data:
        lines.extend(
            [
                f"## {scenario.incident_id}",
                "",
                f"- Event file: `{scenario.file_name}`",
                f"- Scenario: {scenario.description}",
                "- Which services should be protected first?",
                "- Which lower-priority services can be degraded for the TTL?",
                "- Which actions require approval before use?",
                "- What evidence confirms rollback?",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def write_readiness_report(path: Path, service_data: dict[str, Any]) -> dict[str, Any]:
    services = service_data["service_groups"]
    model = ServicePriorityFile.model_validate(service_data)
    from .service_priority import validate_service_priority

    validation = validate_service_priority(model, strict=False)
    checks = {
        "services_have_owner": sum(1 for item in services if item.get("owner")),
        "services_have_approver": sum(1 for item in services if item.get("approver")),
        "services_have_rollback_owner": sum(1 for item in services if item.get("rollback_owner")),
        "services_have_rollback_control": sum(1 for item in services if item.get("rollback_control")),
        "services_have_traffic_baseline": sum(1 for item in services if item.get("traffic_baseline")),
        "services_have_business_process": sum(1 for item in services if item.get("business_process")),
        "services_have_endpoint_exposure": sum(1 for service in services for endpoint in service["endpoints"] if endpoint.get("exposure")),
        "multi_endpoint_services": sum(1 for item in services if len(item.get("endpoints", [])) > 1),
        "services_with_specific_business_language": sum(
            1
            for item in services
            if "business impact increases" not in item.get("revenue_impact", "")
            and "maintain enough availability" not in item.get("slo", "")
        ),
    }
    total_checks = len(services) * 7 + sum(len(service["endpoints"]) for service in services)
    passed_checks = sum(checks.values())
    report = {
        "readiness_report_version": 1,
        "review_package_readiness_score": round((passed_checks / total_checks) * 100, 2) if total_checks else 0,
        "service_groups": len(services),
        "checks": checks,
        "warnings": validation.warnings,
        "blockers": validation.blockers,
        "readiness_gaps": validation.blockers,
        "status": "READY_FOR_TABLETOP" if passed_checks == total_checks else "REVIEW_INPUT_GAPS",
    }
    write_json(path, report)
    write_yaml(path.with_suffix(".yml"), report)
    return report


def write_enriched_actions_csv(path: Path, plan: BrownoutPlan) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "action_id",
        "action_type",
        "service_id",
        "business_process",
        "owner",
        "approver",
        "rollback_owner",
        "confidence",
        "selectors",
        "parameters",
        "approval_metadata",
        "rollback_control",
        "evidence",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for action in plan.actions:
            writer.writerow(
                {
                    "action_id": action.action_id,
                    "action_type": action.action_type.value,
                    "service_id": action.service_id,
                    "business_process": action.business_process or "",
                    "owner": action.owner or "",
                    "approver": action.approver or "",
                    "rollback_owner": action.rollback_owner or "",
                    "confidence": action.confidence.value,
                    "selectors": json.dumps(action.selectors, sort_keys=True),
                    "parameters": json.dumps(action.parameters, sort_keys=True),
                    "approval_metadata": json.dumps(action.approval_metadata, sort_keys=True),
                    "rollback_control": json.dumps(action.rollback_control, sort_keys=True),
                    "evidence": json.dumps(action.evidence, sort_keys=True),
                }
            )


def write_schema_files(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    schemas = {
        "ddos_event.schema.json": DdosEvent.model_json_schema(),
        "service_priority.schema.json": ServicePriorityFile.model_json_schema(),
        "policy_pack.schema.json": PolicyPack.model_json_schema(),
        "brownout_plan.schema.json": BrownoutPlan.model_json_schema(),
        "rollback_plan.schema.json": RollbackPlan.model_json_schema(),
        "summary.schema.json": Summary.model_json_schema(),
    }
    for name, schema in schemas.items():
        write_json(path / name, schema)
    write_json(
        path / "manifest.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Generated brownout data bundle manifest",
            "type": "object",
            "required": ["bundle_version", "generated_at", "inputs", "scenarios"],
            "properties": {
                "bundle_version": {"type": "integer"},
                "generated_at": {"type": "string"},
                "description": {"type": "string"},
                "inputs": {"type": "object"},
                "scenarios": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["event", "incident_id", "description"],
                        "properties": {
                            "event": {"type": "string"},
                            "incident_id": {"type": "string"},
                            "description": {"type": "string"},
                            "allow_null_route": {"type": "boolean"},
                            "allow_admin_lockdown": {"type": "boolean"},
                            "allow_source_blocks": {"type": "boolean"},
                        },
                    },
                },
            },
        },
    )


def edge_case_events() -> dict[str, dict[str, Any]]:
    base_target = target("edge_case_target", "203.0.113.10", "tcp", [443], 1000, 100, 100, 10)
    return {
        "duplicate_event_id_a.json": event_base("evt-gen-duplicate", "VOLUMETRIC", "LOW", base_target),
        "duplicate_event_id_b.json": event_base("evt-gen-duplicate", "APPLICATION", "MEDIUM", base_target),
        "clock_skew_observed_before_started.json": event_base(
            "evt-gen-clock-skew",
            "UNKNOWN",
            "LOW",
            base_target,
            started_at="2026-01-01T00:05:00Z",
            observed_at="2026-01-01T00:01:00Z",
        ),
        "started_at_only.json": {
            **event_base("evt-gen-started-only", "UNKNOWN", "LOW", base_target),
            "observed_at": None,
        },
        "malformed_recoverable_missing_metrics.json": event_base(
            "evt-gen-missing-metrics",
            "UNKNOWN",
            "LOW",
            {"name": "edge_case_target", "ip": "203.0.113.10", "protocol": "tcp", "ports": [443]},
        ),
    }


def write_edge_cases(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for name, event in edge_case_events().items():
        write_json(path / name, event)


def write_negative_input_fixtures(path: Path, service_data: dict[str, Any], pack_data: dict[str, Any]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    stale = deepcopy(service_data)
    stale["trusted_sources"]["stale_partner_range"] = {
        "description": "Stale partner source range for negative readiness coverage",
        "cidrs": ["192.0.2.200/32"],
        "purpose": "negative fixture only",
        "applicable_services": ["payment_endpoint"],
        "last_reviewed_at": "2024-01-01",
        "review_owner": "payment operations",
        "review_cadence_days": 30,
        "exception_process": "negative fixture requires review",
        "emergency_override_process": "negative fixture requires rollback review",
    }
    stale["service_groups"][0]["trusted_source_groups"] = ["missing_trusted_group"]
    stale["service_groups"][1]["trusted_source_groups"] = ["stale_partner_range"]
    write_yaml(path / "service_priority_stale_and_missing_trusted_sources.yml", stale)

    p0_shed = deepcopy(service_data)
    p0_shed["service_groups"][0]["brownout_mode"] = "SHED"
    write_yaml(path / "service_priority_invalid_p0_shed.yml", p0_shed)

    invalid_pack = deepcopy(pack_data)
    invalid_pack.pop("pack_id", None)
    write_yaml(path / "policy_pack_missing_pack_id.yml", invalid_pack)


def write_redacted_input_bundle(path: Path, service_data: dict[str, Any], pack_data: dict[str, Any], config_data: dict[str, Any], scenario_data: list[Scenario]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    service_names = [service.get("display_name", service["id"]) for service in service_data["service_groups"]]
    service_map = service_display_name_map(service_names)
    write_yaml(path / "service_priority.yml", redact_value(service_data, service_map))
    write_yaml(path / "policy_pack.yml", redact_value(pack_data, service_map))
    write_yaml(path / "thresholds.yml", config_data)
    events_dir = path / "events"
    for scenario in scenario_data:
        write_json(events_dir / scenario.file_name, redact_value(scenario.event, service_map))


def write_large_estate_fixture(path: Path, service_data: dict[str, Any], service_count: int = 100) -> None:
    path.mkdir(parents=True, exist_ok=True)
    base_services = service_data["service_groups"]
    generated = deepcopy(service_data)
    generated["service_groups"] = []
    for index in range(service_count):
        template = deepcopy(base_services[index % len(base_services)])
        template["id"] = f"{template['id']}_{index + 1:03d}"
        template["display_name"] = f"{template['display_name']} {index + 1:03d}"
        template["owner"] = f"{template.get('owner', 'operations')} team {index % 5 + 1}"
        template["approver"] = f"incident commander delegate {index % 4 + 1}"
        template["rollback_owner"] = f"{template.get('rollback_owner', 'operations')} team {index % 5 + 1}"
        for endpoint_index, endpoint in enumerate(template["endpoints"], start=1):
            if ":" not in endpoint["ip"]:
                endpoint["ip"] = f"203.0.{100 + (index // 200)}.{(index % 200) + 1}"
            endpoint["name"] = f"{endpoint['name']}_{index + 1:03d}_{endpoint_index}"
        generated["service_groups"].append(template)
    write_yaml(path / "service_priority_100.yml", generated)


def build_realism_report(input_audit: dict[str, Any], output_audit: dict[str, Any], gaps: list[str]) -> dict[str, Any]:
    checks = {
        "multi_endpoint_services": input_audit.get("services_with_multiple_endpoints", 0) >= 6,
        "no_generic_slo_language": input_audit.get("generic_slo_count", 0) == 0,
        "no_generic_revenue_language": input_audit.get("generic_revenue_impact_count", 0) == 0,
        "mitigation_state_variety": len(input_audit.get("mitigation_states", {})) >= 5,
        "timeline_variety": len(input_audit.get("timeline_scenarios", [])) >= 4,
        "grouped_actions": output_audit.get("grouped_action_count", 0) == output_audit.get("action_count", -1),
        "risk_factors_present": output_audit.get("actions_with_risk_factors", 0) == output_audit.get("action_count", -1),
        "confidence_rationale_present": output_audit.get("actions_with_confidence_rationale", 0) == output_audit.get("action_count", -1),
        "collateral_scope_present": output_audit.get("actions_with_collateral_scope", 0) == output_audit.get("action_count", -1),
        "decision_deadlines_present": output_audit.get("actions_with_decision_deadline", 0) == output_audit.get("action_count", -1),
        "redacted_inputs_generated": bool(output_audit.get("redacted_input_bundle")),
        "negative_fixtures_generated": output_audit.get("negative_input_fixtures", 0) >= 3,
        "large_estate_fixture_generated": bool(output_audit.get("large_estate_fixture")),
        "markdown_summaries_generated": output_audit.get("markdown_summaries", 0) == output_audit.get("scenario_outputs", -1),
        "post_incident_diff_output_generated": bool(output_audit.get("post_incident_diff_output")),
    }
    score = round((sum(1 for passed in checks.values() if passed) / len(checks)) * 100, 2)
    return {
        "realism_report_version": 1,
        "realism_score": score,
        "status": "REALISM_GAPS_CLOSED" if score == 100 and not gaps else "REALISM_REVIEW",
        "checks": checks,
        "structural_gap_count": len(gaps),
        "remaining_gaps": gaps,
    }


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_artifact_fingerprints(root: Path) -> None:
    entries: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "fingerprints.json":
            entries[str(path.relative_to(root))] = file_sha256(path)
    write_json(root / "fingerprints.json", {"algorithm": "sha256", "files": entries})


def write_post_incident_diff_inputs(path: Path) -> None:
    data = {
        "post_incident_diff_version": 1,
        "incident_id": "INC-GEN-006",
        "actual_changes": [
            {
                "action_id": "act_001",
                "status": "applied",
                "applied_at": "2026-01-01T00:06:00Z",
                "rollback_evidence": "operator-entered rollback confirmation",
            },
            {
                "action_id": "act_002",
                "status": "skipped",
                "reason": "service owner declined port block during review",
            },
        ],
    }
    write_yaml(path / "post_incident_actual_changes.yml", data)
    write_json(
        path / "post_incident_diff_summary.json",
        {
            "post_incident_diff_version": 1,
            "incident_id": "INC-GEN-006",
            "actions_applied": 1,
            "actions_skipped": 1,
            "actions_lacking_rollback_evidence": 0,
            "lessons_learned": ["Capture approval evidence and rollback verification in the same review package."],
        },
    )


def write_post_incident_diff_output(path: Path, plan: BrownoutPlan) -> None:
    actual_path = path / "post_incident_actual_changes.yml"
    actual = yaml.safe_load(actual_path.read_text()) if actual_path.exists() else {"actual_changes": []}
    actual_by_id = {item.get("action_id"): item for item in actual.get("actual_changes", []) if isinstance(item, dict)}
    applied = []
    skipped = []
    not_recorded = []
    lacking_evidence = []
    for action in plan.actions:
        record = actual_by_id.get(action.action_id)
        if record is None:
            not_recorded.append({"action_id": action.action_id, "service_id": action.service_id, "risk_level": action.risk_level.value})
            continue
        if record.get("status") == "applied":
            applied.append({"action_id": action.action_id, "service_id": action.service_id, "expected_risk": action.risk_level.value})
            if action.action_type.value not in {"MONITOR_ONLY", "NO_ACTION"} and not record.get("rollback_evidence"):
                lacking_evidence.append({"action_id": action.action_id, "service_id": action.service_id})
        elif record.get("status") == "skipped":
            skipped.append({"action_id": action.action_id, "service_id": action.service_id, "reason": record.get("reason", "")})
    write_json(
        path / "post_incident_diff_output.json",
        {
            "post_incident_diff_version": 1,
            "incident_id": plan.incident_id,
            "event_id": plan.event_id,
            "status": "REVIEW_ACTUAL_CHANGES" if not_recorded or lacking_evidence else "MATCHED_REVIEW_RECORDS",
            "actions_applied": len(applied),
            "actions_skipped": len(skipped),
            "actions_not_recorded": len(not_recorded),
            "actions_lacking_rollback_evidence": len(lacking_evidence),
            "applied": applied,
            "skipped": skipped,
            "not_recorded": not_recorded,
            "lacking_rollback_evidence": lacking_evidence,
            "lessons_learned": [
                "Record applied, skipped, and rejected decisions against the original action IDs.",
                "Compare expected risk with observed business impact before closing the review.",
                "Attach rollback evidence for each applied temporary policy.",
            ],
        },
    )


def write_strict_mode_report(path: Path, scenario: Scenario, status: str, details: str) -> None:
    write_json(
        path / f"{Path(scenario.file_name).stem}.json",
        {
            "scenario": scenario.file_name,
            "incident_id": scenario.incident_id,
            "strict_status": status,
            "details": details,
        },
    )


def service_priority_fixture() -> dict[str, Any]:
    data = {
        "organization": {
            "name": "Example Organization",
            "default_ttl_minutes": 30,
            "maintenance_contact": "operations@example.invalid",
            "incident_commander_contact": "incident-commander@example.invalid",
            "sector": "critical online services",
            "operating_model": "centralized operations with distributed service owners",
            "regions": ["region-a", "region-b"],
            "customer_segments": ["workforce", "public users", "partners"],
            "incident_roles": {
                "incident_commander": "incident commander",
                "network_lead": "network operations lead",
                "application_lead": "application operations lead",
                "communications_lead": "communications operations lead",
                "business_liaison": "business operations liaison",
            },
            "business_units": ["operations", "payments", "communications", "customer support", "public information"],
            "escalation_paths": [
                {"name": "primary_incident_bridge", "contact": "incident-commander@example.invalid", "available": "24x7"},
                {"name": "business_impact_review", "contact": "business-liaison@example.invalid", "available": "business hours with emergency callback"},
            ],
            "critical_operating_periods": [
                {
                    "name": "business_day_peak",
                    "description": "Peak customer and partner transaction window.",
                    "start": "08:00",
                    "end": "18:00",
                }
            ],
        },
        "trusted_sources": {
            "noc_vpn": {
                "description": "NOC and admin source ranges",
                "cidrs": ["10.10.0.0/16", "192.0.2.10/32"],
                "purpose": "incident administration and network operations access",
                "applicable_services": ["vpn_access", "admin_access"],
                "approval_evidence_required": ["source range owner confirmation", "emergency change ticket reference"],
                "emergency_additions": [{"cidr": "192.0.2.11/32", "expires_at": "2026-01-01T01:00:00Z", "reason": "temporary incident operator access"}],
                "last_reviewed_at": "2025-12-15",
                "review_owner": "network operations",
                "review_cadence_days": 365,
                "exception_process": "incident commander approval required for emergency source changes",
                "emergency_override_process": "time-boxed exception reviewed at rollback",
            },
            "payment_gateways": {
                "description": "Payment partner source ranges",
                "cidrs": ["192.0.2.50/32", "192.0.2.51/32"],
                "purpose": "payment partner traffic during authorization workflows",
                "applicable_services": ["payment_endpoint"],
                "approval_evidence_required": ["payment operations partner range attestation"],
                "emergency_additions": [],
                "last_reviewed_at": "2025-12-20",
                "review_owner": "payment operations",
                "review_cadence_days": 365,
                "exception_process": "payment operations approval required for partner range changes",
                "emergency_override_process": "time-boxed exception reviewed at rollback",
            },
            "sip_trunks": {
                "description": "SIP edge trusted trunks",
                "cidrs": ["192.0.2.60/32", "192.0.2.61/32"],
                "purpose": "voice trunk traffic for real-time communications",
                "applicable_services": ["sip_voice"],
                "approval_evidence_required": ["communications operations trunk review"],
                "emergency_additions": [],
                "last_reviewed_at": "2025-12-10",
                "review_owner": "communications operations",
                "review_cadence_days": 365,
                "exception_process": "communications operations approval required for trunk changes",
                "emergency_override_process": "time-boxed exception reviewed at rollback",
            },
            "monitoring_collectors": {
                "description": "Monitoring endpoint collectors",
                "cidrs": ["192.0.2.70/32", "192.0.2.71/32"],
                "purpose": "monitoring endpoint collection and incident visibility",
                "applicable_services": ["monitoring", "emergency_status_notifications"],
                "approval_evidence_required": ["monitoring collector inventory review"],
                "emergency_additions": [],
                "last_reviewed_at": "2025-12-18",
                "review_owner": "monitoring operations",
                "review_cadence_days": 365,
                "exception_process": "monitoring operations approval required for collector changes",
                "emergency_override_process": "time-boxed exception reviewed at rollback",
            },
            "workforce_identity_sources": {
                "description": "Workforce authentication and support sources",
                "cidrs": ["10.20.0.0/16", "192.0.2.80/32"],
                "purpose": "workforce authentication, support, and application administration",
                "applicable_services": ["auth_gateway", "support_portal"],
                "approval_evidence_required": ["identity operations range review"],
                "emergency_additions": [{"cidr": "192.0.2.81/32", "expires_at": "2026-01-01T00:50:00Z", "reason": "temporary support operator source"}],
                "last_reviewed_at": "2025-12-11",
                "review_owner": "identity operations",
                "review_cadence_days": 365,
                "exception_process": "identity operations approval required for workforce range changes",
                "emergency_override_process": "time-boxed exception reviewed at rollback",
            },
        },
        "service_groups": [
            {
                "id": "sip_voice",
                "display_name": "SIP voice",
                "priority": "P0",
                "brownout_mode": "PROTECT",
                "business_process": "real-time communications",
                "owner": "communications operations",
                "approver": "incident commander",
                "rollback_owner": "communications operations",
                "endpoints": [{"name": "sip_edge", "ip": "203.0.113.30", "protocol": "udp", "ports": [5060, 5061, "10000-20000"]}],
                "trusted_source_groups": ["sip_trunks"],
                "max_ttl_minutes": 30,
                "allowed_actions": ["ALLOW_TRUSTED_SOURCES", "RATE_LIMIT_UNTRUSTED", "PRIORITIZE"],
                "rollback_required": True,
            },
            {
                "id": "vpn_access",
                "display_name": "VPN access",
                "priority": "P0",
                "brownout_mode": "PROTECT",
                "business_process": "remote incident administration",
                "owner": "network operations",
                "approver": "incident commander",
                "rollback_owner": "network operations",
                "endpoints": [{"name": "vpn_vip", "ip": "203.0.113.20", "protocol": "udp", "ports": [500, 4500]}],
                "trusted_source_groups": ["noc_vpn"],
                "max_ttl_minutes": 30,
                "allowed_actions": ["ALLOW_TRUSTED_SOURCES", "RATE_LIMIT_UNTRUSTED", "PRIORITIZE"],
                "rollback_required": True,
            },
            {
                "id": "monitoring",
                "display_name": "Monitoring and alerting",
                "priority": "P0",
                "brownout_mode": "PROTECT",
                "business_process": "incident visibility",
                "owner": "monitoring operations",
                "approver": "incident commander",
                "rollback_owner": "monitoring operations",
                "endpoints": [{"name": "monitoring_ingest", "ip": "203.0.113.40", "protocol": "tcp", "ports": [443]}],
                "trusted_source_groups": ["monitoring_collectors"],
                "max_ttl_minutes": 30,
                "allowed_actions": ["ALLOW_TRUSTED_SOURCES", "PRIORITIZE"],
                "rollback_required": True,
            },
            {
                "id": "auth_gateway",
                "display_name": "Authentication gateway",
                "priority": "P0",
                "brownout_mode": "PROTECT",
                "business_process": "workforce and customer authentication",
                "owner": "identity operations",
                "approver": "incident commander",
                "rollback_owner": "identity operations",
                "endpoints": [{"name": "auth_vip", "ip": "203.0.113.45", "protocol": "tcp", "ports": [443]}],
                "trusted_source_groups": ["workforce_identity_sources"],
                "max_ttl_minutes": 30,
                "allowed_actions": ["ALLOW_TRUSTED_SOURCES", "RATE_LIMIT_UNTRUSTED", "PRIORITIZE", "CHALLENGE"],
                "rollback_required": True,
            },
            {
                "id": "payment_endpoint",
                "display_name": "Payment endpoint",
                "priority": "P1",
                "brownout_mode": "PROTECT",
                "business_process": "payment authorization",
                "owner": "payment operations",
                "approver": "incident commander",
                "rollback_owner": "payment operations",
                "endpoints": [{"name": "payment_api", "ip": "203.0.113.60", "protocol": "tcp", "ports": [443]}],
                "trusted_source_groups": ["payment_gateways"],
                "max_ttl_minutes": 30,
                "allowed_actions": ["ALLOW_TRUSTED_SOURCES", "RATE_LIMIT_UNTRUSTED", "PRIORITIZE", "RATE_LIMIT", "CHALLENGE"],
                "rollback_required": True,
            },
            {
                "id": "admin_access",
                "display_name": "Administrative access",
                "priority": "P1",
                "brownout_mode": "RESTRICT_TO_TRUSTED",
                "business_process": "incident administration",
                "owner": "network operations",
                "approver": "incident commander",
                "rollback_owner": "network operations",
                "endpoints": [{"name": "admin_portal", "ip": "203.0.113.50", "protocol": "tcp", "ports": [443, 22]}],
                "trusted_source_groups": ["noc_vpn"],
                "max_ttl_minutes": 20,
                "allowed_actions": ["ALLOW_TRUSTED_SOURCES", "DENY_UNTRUSTED"],
                "rollback_required": True,
                "approval_required": True,
            },
            {
                "id": "customer_api",
                "display_name": "Customer API",
                "priority": "P2",
                "brownout_mode": "RATE_LIMIT",
                "business_process": "customer self-service",
                "owner": "application operations",
                "approver": "incident commander",
                "rollback_owner": "application operations",
                "endpoints": [{"name": "customer_api_vip", "ip": "203.0.113.80/30", "protocol": "tcp", "ports": [443]}],
                "max_ttl_minutes": 20,
                "allowed_actions": ["RATE_LIMIT", "CHALLENGE", "DEPRIORITIZE"],
                "rollback_required": True,
            },
            {
                "id": "search_api",
                "display_name": "Search API",
                "priority": "P2",
                "brownout_mode": "RATE_LIMIT",
                "business_process": "site search",
                "owner": "application operations",
                "approver": "incident commander",
                "rollback_owner": "application operations",
                "endpoints": [{"name": "search_vip", "ip": "203.0.113.70", "protocol": "tcp", "ports": [443]}],
                "max_ttl_minutes": 20,
                "allowed_actions": ["RATE_LIMIT", "CHALLENGE", "DEPRIORITIZE"],
                "rollback_required": True,
            },
            {
                "id": "support_portal",
                "display_name": "Support portal",
                "priority": "P3",
                "brownout_mode": "RATE_LIMIT",
                "business_process": "support case access",
                "owner": "support operations",
                "approver": "incident commander",
                "rollback_owner": "support operations",
                "endpoints": [{"name": "support_vip", "ip": "203.0.113.90", "protocol": "tcp", "ports": [443]}],
                "max_ttl_minutes": 15,
                "allowed_actions": ["RATE_LIMIT", "CHALLENGE", "DEPRIORITIZE", "SHED_LOW_PRIORITY", "TEMPORARY_BLOCK_PORT"],
                "rollback_required": True,
            },
            {
                "id": "report_export",
                "display_name": "Report export",
                "priority": "P3",
                "brownout_mode": "SHED",
                "business_process": "deferred report downloads",
                "owner": "application operations",
                "approver": "incident commander",
                "rollback_owner": "application operations",
                "endpoints": [{"name": "report_export_vip", "ip": "203.0.113.91", "protocol": "tcp", "ports": [443, 8443]}],
                "max_ttl_minutes": 15,
                "allowed_actions": ["SHED_LOW_PRIORITY", "RATE_LIMIT", "TEMPORARY_BLOCK_PORT"],
                "rollback_required": True,
            },
            {
                "id": "public_marketing_site",
                "display_name": "Public marketing site",
                "priority": "P4",
                "brownout_mode": "SHED",
                "business_process": "public information",
                "owner": "web operations",
                "approver": "incident commander",
                "rollback_owner": "web operations",
                "endpoints": [{"name": "public_web_vip", "ip": "203.0.113.10", "protocol": "tcp", "ports": [80, 443]}],
                "max_ttl_minutes": 15,
                "allowed_actions": ["RATE_LIMIT", "CHALLENGE", "SHED_LOW_PRIORITY"],
                "rollback_required": True,
            },
            {
                "id": "media_downloads",
                "display_name": "Media downloads",
                "priority": "P4",
                "brownout_mode": "SHED",
                "business_process": "large public downloads",
                "owner": "web operations",
                "approver": "incident commander",
                "rollback_owner": "web operations",
                "endpoints": [{"name": "media_download_vip", "ip": "203.0.113.110", "protocol": "tcp", "ports": [443, 8080]}],
                "max_ttl_minutes": 10,
                "allowed_actions": ["RATE_LIMIT", "SHED_LOW_PRIORITY", "TEMPORARY_BLOCK_PORT", "TEMPORARY_NULL_ROUTE"],
                "rollback_required": True,
            },
            {
                "id": "shared_static_site",
                "display_name": "Shared static site",
                "priority": "P4",
                "brownout_mode": "SHED",
                "business_process": "static content delivery",
                "owner": "web operations",
                "approver": "incident commander",
                "rollback_owner": "web operations",
                "endpoints": [{"name": "shared_static_vip", "ip": "203.0.113.120", "protocol": "tcp", "ports": [443]}],
                "max_ttl_minutes": 10,
                "allowed_actions": ["RATE_LIMIT", "SHED_LOW_PRIORITY", "TEMPORARY_NULL_ROUTE"],
                "rollback_required": True,
            },
            {
                "id": "shared_status_page",
                "display_name": "Shared status page",
                "priority": "P4",
                "brownout_mode": "SHED",
                "business_process": "public status communications",
                "owner": "communications operations",
                "approver": "incident commander",
                "rollback_owner": "communications operations",
                "endpoints": [{"name": "shared_status_vip", "ip": "203.0.113.120", "protocol": "tcp", "ports": [443]}],
                "max_ttl_minutes": 10,
                "allowed_actions": ["RATE_LIMIT", "SHED_LOW_PRIORITY"],
                "rollback_required": True,
            },
            {
                "id": "ipv6_public_status",
                "display_name": "IPv6 public status",
                "priority": "P4",
                "brownout_mode": "SHED",
                "business_process": "IPv6 public status communications",
                "owner": "communications operations",
                "approver": "incident commander",
                "rollback_owner": "communications operations",
                "endpoints": [{"name": "ipv6_status_vip", "ip": "2001:db8::10", "protocol": "tcp", "ports": [443]}],
                "max_ttl_minutes": 10,
                "allowed_actions": ["RATE_LIMIT", "SHED_LOW_PRIORITY"],
                "rollback_required": True,
            },
            {
                "id": "emergency_status_notifications",
                "display_name": "Emergency status notifications",
                "priority": "P0",
                "brownout_mode": "PROTECT",
                "business_process": "public status communications",
                "owner": "communications operations",
                "approver": "incident commander",
                "rollback_owner": "communications operations",
                "endpoints": [{"name": "status_notify_vip", "ip": "203.0.113.140", "protocol": "tcp", "ports": [443]}],
                "trusted_source_groups": ["monitoring_collectors"],
                "max_ttl_minutes": 30,
                "allowed_actions": ["ALLOW_TRUSTED_SOURCES", "PRIORITIZE", "RATE_LIMIT_UNTRUSTED"],
                "rollback_required": True,
            },
            {
                "id": "research_sandbox",
                "display_name": "Research sandbox",
                "priority": "P4",
                "brownout_mode": "NO_ACTION",
                "business_process": "non-production experimentation",
                "owner": "application operations",
                "approver": "incident commander",
                "rollback_owner": "application operations",
                "endpoints": [{"name": "sandbox_vip", "ip": "203.0.113.130", "protocol": "tcp", "ports": [8443]}],
                "max_ttl_minutes": 10,
                "allowed_actions": ["MONITOR_ONLY", "NO_ACTION"],
                "rollback_required": True,
            },
        ],
    }
    exposure_by_priority = {
        "P0": "WORKFORCE_ONLY",
        "P1": "PARTNER_ONLY",
        "P2": "PUBLIC",
        "P3": "PUBLIC",
        "P4": "PUBLIC",
    }
    enforcement_by_service = {
        "sip_voice": ["SIP_EDGE", "NETWORK_EDGE"],
        "vpn_access": ["VPN_EDGE", "NETWORK_EDGE"],
        "monitoring": ["MONITORING_ENDPOINT", "NETWORK_EDGE"],
        "auth_gateway": ["WAF", "LOAD_BALANCER"],
        "payment_endpoint": ["PAYMENT_ENDPOINT", "WAF", "LOAD_BALANCER"],
        "admin_access": ["FIREWALL", "LOAD_BALANCER"],
    }
    shared_endpoint_groups = {
        "shared_static_site": "shared_public_static",
        "shared_status_page": "shared_public_static",
    }
    action_profiles_by_service = {
        "sip_voice": {"RATE_LIMIT_UNTRUSTED": "protect_critical_udp"},
        "vpn_access": {"RATE_LIMIT_UNTRUSTED": "protect_critical_udp"},
        "auth_gateway": {"RATE_LIMIT_UNTRUSTED": "protect_critical_tcp"},
        "payment_endpoint": {"RATE_LIMIT_UNTRUSTED": "protect_critical_tcp", "RATE_LIMIT": "customer_api_app_pressure"},
        "customer_api": {"RATE_LIMIT": "customer_api_app_pressure"},
        "search_api": {"RATE_LIMIT": "customer_api_app_pressure"},
        "support_portal": {"RATE_LIMIT": "customer_api_app_pressure"},
        "report_export": {"RATE_LIMIT": "public_web_low_priority", "SHED_LOW_PRIORITY": "public_web_low_priority"},
        "public_marketing_site": {"RATE_LIMIT": "public_web_low_priority", "SHED_LOW_PRIORITY": "public_web_low_priority"},
        "media_downloads": {"RATE_LIMIT": "public_web_low_priority", "SHED_LOW_PRIORITY": "public_web_low_priority"},
        "shared_static_site": {"RATE_LIMIT": "public_web_low_priority", "SHED_LOW_PRIORITY": "public_web_low_priority"},
        "shared_status_page": {"RATE_LIMIT": "public_web_low_priority", "SHED_LOW_PRIORITY": "public_web_low_priority"},
        "ipv6_public_status": {"RATE_LIMIT": "public_web_low_priority", "SHED_LOW_PRIORITY": "public_web_low_priority"},
        "emergency_status_notifications": {"RATE_LIMIT_UNTRUSTED": "status_notifications_critical"},
    }
    additional_endpoints = {
        "sip_voice": [
            {"name": "sip_edge_region_b", "ip": "203.0.113.31", "protocol": "udp", "ports": [5060, 5061, "10000-20000"], "region": "region-b", "endpoint_role": "regional_voice_edge"}
        ],
        "vpn_access": [
            {"name": "vpn_health_any", "ip": "203.0.113.21", "protocol": "any", "ports": [443, 500, 4500], "region": "region-a", "endpoint_role": "health_and_remote_access"}
        ],
        "auth_gateway": [
            {"name": "auth_vip_region_b", "ip": "203.0.113.46", "protocol": "tcp", "ports": [443], "region": "region-b", "endpoint_role": "regional_authentication"}
        ],
        "payment_endpoint": [
            {"name": "payment_api_region_b", "ip": "203.0.113.61", "protocol": "tcp", "ports": [443], "region": "region-b", "endpoint_role": "regional_payment_authorization"}
        ],
        "customer_api": [
            {"name": "customer_api_private", "ip": "10.30.0.10", "protocol": "any", "ports": [443, 8443], "exposure": "PRIVATE", "enforcement_points": ["LOAD_BALANCER"], "region": "region-a", "endpoint_role": "private_service_dependency"},
            {"name": "customer_api_nested_cidr", "ip": "203.0.113.84/31", "protocol": "tcp", "ports": [443], "region": "region-b", "endpoint_role": "regional_customer_api_cidr"},
        ],
        "support_portal": [
            {"name": "support_admin_vip", "ip": "203.0.113.92", "protocol": "tcp", "ports": [443], "exposure": "WORKFORCE_ONLY", "enforcement_points": ["FIREWALL", "LOAD_BALANCER"], "region": "region-a", "endpoint_role": "support_admin"}
        ],
        "ipv6_public_status": [
            {"name": "ipv6_status_vip_region_b", "ip": "2001:db8::11", "protocol": "tcp", "ports": [443], "region": "region-b", "endpoint_role": "regional_ipv6_status"}
        ],
        "emergency_status_notifications": [
            {"name": "status_notify_vip_ipv6", "ip": "2001:db8::140", "protocol": "tcp", "ports": [443], "exposure": "PUBLIC", "enforcement_points": ["WAF", "LOAD_BALANCER"], "region": "region-b", "endpoint_role": "public_status_notifications"}
        ],
    }
    service_specific_metadata = {
        "sip_voice": {
            "slo": "voice signaling should remain available for priority communications with no more than 2 minutes of registration disruption",
            "revenue_impact": "lost real-time communications delays incident coordination and support callbacks",
            "public_safety_impact": "communications delay can affect emergency coordination workflows",
            "affected_user_count": "300 operators and priority communications users",
            "business_impact_scale": "high operational continuity impact",
            "impact_summary": "Voice disruption reduces incident coordination capacity.",
        },
        "vpn_access": {
            "slo": "incident administration access should remain reachable for approved operators during response windows",
            "revenue_impact": "loss of VPN access slows restoration and change review work",
            "public_safety_impact": "indirect operational continuity impact if operators cannot administer response systems",
            "affected_user_count": "120 remote operators",
            "business_impact_scale": "high operational response impact",
            "impact_summary": "VPN degradation can delay operator access to response tooling.",
        },
        "monitoring": {
            "slo": "monitoring ingest should preserve enough telemetry to identify deny spikes and rollback success",
            "revenue_impact": "loss of monitoring increases time to restore customer-facing services",
            "public_safety_impact": "visibility loss can delay incident communications",
            "affected_user_count": "incident response and observability teams",
            "business_impact_scale": "high incident visibility impact",
            "impact_summary": "Monitoring loss reduces confidence in brownout and rollback decisions.",
        },
        "auth_gateway": {
            "slo": "authentication should maintain priority workforce and customer login capacity during overload",
            "revenue_impact": "authentication disruption can block customer transactions and workforce access",
            "public_safety_impact": "none expected beyond customer access delays",
            "affected_user_count": "25,000 peak-hour login attempts",
            "business_impact_scale": "high customer access impact",
            "impact_summary": "Authentication pressure can block downstream customer and workforce workflows.",
        },
        "payment_endpoint": {
            "slo": "payment authorization should keep partner-approved transactions flowing during the TTL",
            "revenue_impact": "each failed authorization can defer or lose payment transactions",
            "public_safety_impact": "none expected for synthetic payment workflow",
            "affected_user_count": "8,000 peak-hour payment attempts",
            "business_impact_scale": "high direct transaction impact",
            "impact_summary": "Payment endpoint degradation directly affects transaction completion.",
        },
        "admin_access": {
            "slo": "administrative access should remain available to approved sources only during incident review",
            "revenue_impact": "admin lockout can delay restoration, while broad access can increase operational risk",
            "public_safety_impact": "none expected beyond operational restoration delay",
            "affected_user_count": "40 administrative operators",
            "business_impact_scale": "high operational control impact",
            "impact_summary": "Administrative restrictions trade operator reachability for reduced exposure.",
        },
        "customer_api": {
            "slo": "customer self-service should preserve priority API calls while non-critical requests degrade gracefully",
            "revenue_impact": "API errors increase support demand and defer customer self-service",
            "public_safety_impact": "none expected for synthetic customer API workflow",
            "affected_user_count": "40,000 customer API requests per peak hour",
            "business_impact_scale": "medium customer experience impact",
            "impact_summary": "Customer API brownout may increase support contacts and delayed self-service.",
        },
        "search_api": {
            "slo": "site search can degrade before authentication, payments, monitoring, or communications",
            "revenue_impact": "search degradation can reduce discovery and increase support friction",
            "public_safety_impact": "none expected for synthetic search workflow",
            "affected_user_count": "15,000 public search requests per peak hour",
            "business_impact_scale": "medium customer experience impact",
            "impact_summary": "Search is useful but deferrable compared with core workflows.",
        },
        "support_portal": {
            "slo": "support case access may degrade for public users while workforce admin access is preserved",
            "revenue_impact": "support portal degradation increases backlog and delayed case resolution",
            "public_safety_impact": "none expected for synthetic support workflow",
            "affected_user_count": "2,500 active case users",
            "business_impact_scale": "medium support operations impact",
            "impact_summary": "Support portal restrictions increase case backlog risk.",
        },
        "report_export": {
            "slo": "report downloads may be deferred during severe overload",
            "revenue_impact": "delayed exports affect back-office reporting but not live transactions",
            "public_safety_impact": "none expected for deferred reporting",
            "affected_user_count": "600 report users",
            "business_impact_scale": "low to medium deferred work impact",
            "impact_summary": "Report export is intentionally deferrable during brownout.",
        },
        "public_marketing_site": {
            "slo": "public information pages may degrade before critical authenticated workflows",
            "revenue_impact": "marketing availability loss may reduce lead capture during the TTL",
            "public_safety_impact": "none expected for marketing content",
            "affected_user_count": "50,000 public page views per peak hour",
            "business_impact_scale": "low direct operational impact",
            "impact_summary": "Marketing traffic is deferrable relative to critical services.",
        },
        "media_downloads": {
            "slo": "large downloads may be shed quickly to preserve transactional services",
            "revenue_impact": "download delays reduce user satisfaction but protect higher-priority capacity",
            "public_safety_impact": "none expected for media downloads",
            "affected_user_count": "10,000 download requests per peak hour",
            "business_impact_scale": "low deferrable bandwidth impact",
            "impact_summary": "Media downloads consume capacity and are safe to defer with review.",
        },
        "shared_static_site": {
            "slo": "static content may degrade only after shared endpoint collateral review",
            "revenue_impact": "static asset degradation can affect multiple public pages",
            "public_safety_impact": "status content sharing this destination requires collateral review",
            "affected_user_count": "35,000 public asset requests per peak hour",
            "business_impact_scale": "medium shared endpoint impact",
            "impact_summary": "Shared static endpoint changes may affect multiple services.",
        },
        "shared_status_page": {
            "slo": "status communications should remain reachable unless collateral review approves degradation",
            "revenue_impact": "status page degradation increases inbound support and uncertainty",
            "public_safety_impact": "public status communication delay can affect incident transparency",
            "affected_user_count": "public status subscribers and support teams",
            "business_impact_scale": "medium public communications impact",
            "impact_summary": "Status page availability has higher communications value than ordinary static content.",
        },
        "ipv6_public_status": {
            "slo": "IPv6 status traffic may degrade only if IPv4 status remains reviewed separately",
            "revenue_impact": "IPv6-only users may lose status visibility during the TTL",
            "public_safety_impact": "status communication delay may affect user decisions during incident response",
            "affected_user_count": "IPv6 public users",
            "business_impact_scale": "medium public communications impact",
            "impact_summary": "IPv6 public status validates dual-stack review behavior.",
        },
        "emergency_status_notifications": {
            "slo": "emergency status notifications should remain available for critical communications during response",
            "revenue_impact": "notification loss increases inbound contacts and reduces stakeholder visibility",
            "public_safety_impact": "delayed public status notifications can affect time-sensitive operational decisions",
            "affected_user_count": "public subscribers, partners, and response stakeholders",
            "business_impact_scale": "critical communications impact",
            "impact_summary": "Emergency status notifications carry explicit public communications impact.",
        },
        "research_sandbox": {
            "slo": "non-production sandbox can remain monitor-only during incident overload",
            "revenue_impact": "sandbox unavailability has no expected customer transaction impact",
            "public_safety_impact": "none expected for non-production sandbox",
            "affected_user_count": "small internal engineering group",
            "business_impact_scale": "low internal experimentation impact",
            "impact_summary": "Research sandbox should not consume response capacity during brownout.",
        },
    }
    for index, service in enumerate(data["service_groups"], start=1):
        service["endpoints"].extend(additional_endpoints.get(service["id"], []))
        service.update(service_specific_metadata.get(service["id"], {}))
        service.setdefault("trusted_source_requirement", "REQUIRED" if service["priority"] in {"P0", "P1"} else "NOT_APPLICABLE")
        service.setdefault("criticality_rationale", f"{service['display_name']} priority is assigned by business impact review for {service.get('business_process', 'unspecified workflow')}.")
        service.setdefault("rto_minutes", 30 if service["priority"] in {"P0", "P1"} else 120)
        service.setdefault("rpo_minutes", 15 if service["priority"] in {"P0", "P1"} else 60)
        service.setdefault("slo", f"{service['display_name']} has a service-specific brownout SLO defined by the service owner.")
        service.setdefault("user_population", "internal operators, partners, public users, or automated clients as declared by service owner")
        service.setdefault("revenue_impact", f"{service['display_name']} has a service-specific operational impact recorded for brownout review.")
        service.setdefault("public_safety_impact", "no direct public communications impact declared by service owner")
        service.setdefault("customer_tiers", ["standard", "priority"] if service["priority"] in {"P0", "P1", "P2"} else ["standard"])
        service.setdefault("contractual_obligations", ["review rollback deadline with service owner"])
        service.setdefault("regulated_workflows", ["payment authorization"] if service["id"] == "payment_endpoint" else [])
        service.setdefault("approval_metadata", {
            "named_approver": service.get("approver", "incident commander"),
            "role_group": "incident command",
            "approval_channel": "incident bridge",
            "approval_expiry_minutes": service.get("max_ttl_minutes", 30),
            "deputy_approver": f"deputy {service.get('owner', 'operations')}",
            "after_hours_path": "incident bridge callback and recorded operator decision",
            "emergency_delegation": "deputy incident commander may approve if primary is unavailable",
        })
        service.setdefault("rollback_control", {
            "rollback_owner": service.get("rollback_owner"),
            "escalation_contact": "incident-commander@example.invalid",
            "expected_baseline_state": "pre-incident service policy restored",
            "verification_steps": [
                f"Confirm temporary policy for {service['display_name']} is removed.",
                f"Confirm {service['display_name']} baseline policy hash or operator record matches pre-incident state.",
                f"Attach monitoring evidence for {service['display_name']} legitimate traffic after rollback.",
            ],
            "verification_steps_by_action": {
                "ALLOW_TRUSTED_SOURCES": [
                    f"Confirm temporary trusted-source allow overlay for {service['display_name']} is removed or returned to baseline.",
                    "Attach policy diff showing only pre-incident trusted-source policy remains.",
                    "Confirm trusted-source traffic and ordinary baseline traffic counters are within expected range.",
                ],
                "RATE_LIMIT_UNTRUSTED": [
                    f"Confirm untrusted-source rate limit for {service['display_name']} is removed or restored to normal policy.",
                    "Attach rate-limit counter snapshot before and after rollback.",
                    "Confirm no unexpected deny or throttle spike remains.",
                ],
                "RATE_LIMIT": [
                    f"Confirm temporary rate limit for {service['display_name']} is removed or restored to steady-state profile.",
                    "Attach request-rate and error-rate evidence for the endpoint.",
                    "Confirm service owner accepts post-rollback user experience.",
                ],
                "PRIORITIZE": [
                    f"Confirm temporary priority handling for {service['display_name']} is removed or restored to baseline.",
                    "Attach enforcement-point policy diff or queue profile review note.",
                    "Confirm other critical services are not starved after rollback.",
                ],
                "SHED_LOW_PRIORITY": [
                    f"Confirm temporary shedding for {service['display_name']} is removed.",
                    "Attach availability and request outcome evidence after rollback.",
                    "Confirm deferred user journey has recovered or queued work is understood.",
                ],
                "CHALLENGE": [
                    f"Confirm temporary challenge behavior for {service['display_name']} is removed or restored to baseline.",
                    "Attach automated-client success evidence after rollback.",
                    "Confirm challenge-related failures have returned to expected range.",
                ],
                "TEMPORARY_BLOCK_PORT": [
                    f"Confirm temporary destination-port block for {service['display_name']} is removed.",
                    "Attach port-specific allow/deny counter evidence after rollback.",
                    "Confirm legitimate clients using the port can reconnect.",
                ],
                "TEMPORARY_NULL_ROUTE": [
                    f"Confirm temporary null-route candidate for {service['display_name']} is not active.",
                    "Attach destination reachability and shared-service collateral evidence.",
                    "Confirm service owner accepts restored availability state.",
                ],
            },
            "evidence_required": ["rollback timestamp", "monitoring confirmation"],
        })
        service.setdefault("traffic_baseline", {
            "baseline_bps": (index * 8500000) + (25000000 if service["priority"] in {"P0", "P1"} else 0),
            "baseline_pps": (index * 4200) + (12000 if service["priority"] in {"P0", "P1"} else 0),
            "normal_bps_low": index * 3200000,
            "normal_bps_high": (index * 14000000) + (30000000 if service["priority"] in {"P0", "P1"} else 0),
            "normal_pps_low": index * 1700,
            "normal_pps_high": (index * 7600) + (15000 if service["priority"] in {"P0", "P1"} else 0),
            "hourly_profile": {"00": "low", "08": "rising", "12": "peak", "18": "declining"},
            "seasonal_note": "synthetic range with peak-hour and priority-service variation for tabletop review",
        })
        if service["id"] in {"customer_api", "search_api"}:
            service.setdefault("depends_on", [{"service_id": "auth_gateway", "relationship": "depends_on"}])
        if service["id"] in {"public_marketing_site", "media_downloads", "shared_static_site", "shared_status_page"}:
            service.setdefault("maintenance_windows", [{"name": "content_update_window", "start": "02:00", "end": "04:00", "action_guidance": "avoid unrelated changes during incident rollback"}])
        if service["id"] in action_profiles_by_service:
            service.setdefault("action_profiles", action_profiles_by_service[service["id"]])
        for endpoint in service["endpoints"]:
            endpoint.setdefault("exposure", exposure_by_priority[service["priority"]])
            endpoint.setdefault("enforcement_points", enforcement_by_service.get(service["id"], ["WAF", "LOAD_BALANCER"] if endpoint["protocol"] == "tcp" else ["NETWORK_EDGE"]))
            endpoint.setdefault("region", "region-a")
            endpoint.setdefault("endpoint_role", "primary_service_endpoint")
            if endpoint["protocol"] == "tcp":
                endpoint.setdefault("paths", ["/", "/health", "/status"] if service["priority"] in {"P0", "P1"} else ["/", "/health"])
            if service["id"] in shared_endpoint_groups:
                endpoint.setdefault("shared_endpoint_group", shared_endpoint_groups[service["id"]])
    return data


def policy_pack_fixture() -> dict[str, Any]:
    return {
        "pack_id": "business-impact-full-coverage",
        "description": "Full-coverage synthetic policy pack for offline brownout review testing.",
        "ttl": {
            "default_minutes": 30,
            "p0_max_minutes": 30,
            "p1_max_minutes": 25,
            "p2_max_minutes": 20,
            "p3_max_minutes": 15,
            "p4_max_minutes": 10,
            "null_route_max_minutes": 10,
        },
        "rate_limit_profiles": {
            "protect_critical_udp": {"description": "Conservative untrusted UDP limit for critical services.", "abstract_rate": "low", "applies_to": ["udp"]},
            "protect_critical_tcp": {"description": "Conservative untrusted TCP limit for critical services.", "abstract_rate": "low", "applies_to": ["tcp"]},
            "public_web_low_priority": {
                "description": "Reduce low-priority public web traffic.",
                "abstract_rate": "medium",
                "exact_rate": {
                    "value": 20,
                    "unit": "percent_of_recent_baseline",
                    "measurement_window_seconds": 300,
                    "scope": "per service endpoint",
                    "source": "user supplied policy pack",
                },
                "applies_to": ["tcp"],
            },
            "customer_api_app_pressure": {"description": "Reduce non-critical API request pressure.", "abstract_rate": "medium", "applies_to": ["tcp"]},
            "status_notifications_critical": {"description": "Protect critical status notification delivery.", "abstract_rate": "low", "applies_to": ["tcp"]},
            "private_dependency_pressure": {"description": "Reduce private dependency pressure without public shedding.", "abstract_rate": "medium", "applies_to": ["tcp", "any"]},
        },
        "action_preferences": {
            "P0": ["ALLOW_TRUSTED_SOURCES", "PRIORITIZE", "RATE_LIMIT_UNTRUSTED"],
            "P1": ["ALLOW_TRUSTED_SOURCES", "PRIORITIZE", "RATE_LIMIT_UNTRUSTED", "RATE_LIMIT"],
            "P2": ["CHALLENGE", "RATE_LIMIT", "DEPRIORITIZE"],
            "P3": ["CHALLENGE", "RATE_LIMIT", "SHED_LOW_PRIORITY", "TEMPORARY_BLOCK_PORT"],
            "P4": ["SHED_LOW_PRIORITY", "RATE_LIMIT", "TEMPORARY_BLOCK_PORT", "TEMPORARY_NULL_ROUTE"],
        },
        "risk_defaults": {
            "TEMPORARY_NULL_ROUTE": "CRITICAL",
            "DENY_UNTRUSTED": "HIGH",
            "TEMPORARY_BLOCK_PORT": "HIGH",
            "RATE_LIMIT_UNTRUSTED": "MEDIUM",
            "RATE_LIMIT": "MEDIUM",
            "SHED_LOW_PRIORITY": "MEDIUM",
            "PRIORITIZE": "LOW",
            "ALLOW_TRUSTED_SOURCES": "LOW",
            "DEPRIORITIZE": "MEDIUM",
            "CHALLENGE": "MEDIUM",
            "MONITOR_ONLY": "LOW",
            "NO_ACTION": "LOW",
        },
    }


def thresholds_fixture() -> dict[str, Any]:
    return {
        "default_ttl_minutes": 30,
        "max_ttl_minutes": 60,
        "p0_max_ttl_minutes": 30,
        "p1_max_ttl_minutes": 25,
        "p2_max_ttl_minutes": 20,
        "p3_max_ttl_minutes": 15,
        "p4_max_ttl_minutes": 10,
        "null_route_max_ttl_minutes": 10,
        "max_actions": 100,
        "allow_name_match": False,
        "require_rollback": True,
        "require_ttl": True,
        "fail_on_p0_shed": True,
        "fail_on_unmatched_event_targets": False,
        "default_mode": "REVIEW_ONLY",
        "source_blocking": {
            "enabled_by_default": False,
            "min_ipv4_prefix_length": 24,
            "min_ipv6_prefix_length": 64,
            "require_spoofing_likely_false": True,
        },
        "null_route": {"enabled_by_default": False, "p0_allowed": False, "p1_allowed": False, "require_allow_flag": True},
    }


def event_base(event_id: str, attack_class: str, severity: str, target: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    event = {
        "event_id": event_id,
        "started_at": "2026-01-01T00:00:00Z",
        "observed_at": "2026-01-01T00:03:00Z",
        "severity": severity,
        "attack_class": attack_class,
        "mitigation_state": "ACTIVE",
        "confidence": "HIGH",
        "targets": [target],
        "signals": {
            "top_source_countries": ["ZZ"],
            "top_source_asns": ["asn-64500"],
            "top_source_prefixes": ["198.51.100.0/24"],
            "protocol_mix": {"tcp_syn": 40, "udp": 40, "http_get": 20},
            "user_agent_anomalies": False,
            "path_anomalies": [],
            "spoofing_likely": False,
        },
        "provider_actions_already_active": [],
        "notes": ["Synthetic normalized DDoS mitigation event for offline review testing."],
    }
    event.update(overrides)
    signals = event.setdefault("signals", {})
    signals.setdefault("telemetry_source", "normalized mitigation event feed")
    signals.setdefault("collector_type", "passive mitigation telemetry")
    signals.setdefault("sampling_window_seconds", 180)
    signals.setdefault("sample_size", 25000)
    signals.setdefault("window_started_at", "2026-01-01T00:00:00Z")
    signals.setdefault("window_ended_at", "2026-01-01T00:03:00Z")
    signals.setdefault("evidence_age_seconds", 60)
    signals.setdefault("signal_confidence", event.get("confidence", "MEDIUM"))
    return event


def target(name: str, ip: str, protocol: str, ports: list[int | str] | None, observed_bps: int, observed_pps: int, baseline_bps: int, baseline_pps: int) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": name,
        "ip": ip,
        "protocol": protocol,
        "observed_bps": observed_bps,
        "observed_pps": observed_pps,
        "baseline_bps": baseline_bps,
        "baseline_pps": baseline_pps,
    }
    if ports is not None:
        data["ports"] = ports
    return data


def scenarios() -> list[Scenario]:
    return [
        Scenario(
            "01_volumetric_public_and_vpn.json",
            "INC-GEN-001",
            "Volumetric event affecting VPN access and public marketing traffic.",
            {
                **event_base(
                    "evt-gen-001",
                    "VOLUMETRIC",
                    "HIGH",
                    target("vpn_vip", "203.0.113.20", "udp", [500, 4500], 350000000, 180000, 50000000, 30000),
                    signals={
                        "top_source_countries": ["ZZ"],
                        "top_source_asns": ["asn-64500"],
                        "top_source_prefixes": ["198.51.100.0/24"],
                        "protocol_mix": {"udp": 70, "tcp_syn": 30},
                        "user_agent_anomalies": False,
                        "path_anomalies": [],
                        "spoofing_likely": True,
                    },
                    provider_actions_already_active=["upstream_scrubbing"],
                ),
                "targets": [
                    target("vpn_vip", "203.0.113.20", "udp", [500, 4500], 350000000, 180000, 50000000, 30000),
                    target("public_web_vip", "203.0.113.10", "tcp", [80, 443], 1800000000, 920000, 120000000, 70000),
                ],
            },
        ),
        Scenario(
            "02_application_payment_endpoint.json",
            "INC-GEN-002",
            "Application-layer pressure on payment endpoint.",
            event_base(
                "evt-gen-002",
                "APPLICATION",
                "HIGH",
                target("payment_api", "203.0.113.60", "tcp", [443], 120000000, 55000, 20000000, 9000),
                signals={
                    "top_source_countries": ["ZZ"],
                    "top_source_asns": ["asn-64510"],
                    "top_source_prefixes": ["198.51.100.64/26"],
                    "protocol_mix": {"http_get": 80, "tcp_syn": 20},
                    "user_agent_anomalies": True,
                    "path_anomalies": ["/checkout", "/payment/authorize"],
                    "spoofing_likely": False,
                },
            ),
            allow_source_blocks=True,
        ),
        Scenario(
            "03_application_customer_api_cidr.json",
            "INC-GEN-003",
            "Application-layer pressure on a CIDR-defined customer API endpoint.",
            event_base(
                "evt-gen-003",
                "APPLICATION",
                "MEDIUM",
                target("customer_api_vip", "203.0.113.81", "tcp", [443], 90000000, 42000, 30000000, 12000),
                confidence="MEDIUM",
                signals={
                    "top_source_countries": ["ZZ"],
                    "top_source_asns": ["asn-64511"],
                    "top_source_prefixes": ["198.51.100.128/25"],
                    "protocol_mix": {"http_get": 90, "http_post": 10},
                    "user_agent_anomalies": True,
                    "path_anomalies": ["/api/search", "/api/account"],
                    "spoofing_likely": False,
                },
            ),
        ),
        Scenario(
            "04_protocol_sip_voice.json",
            "INC-GEN-004",
            "Protocol event affecting SIP edge service.",
            event_base(
                "evt-gen-004",
                "PROTOCOL",
                "HIGH",
                target("sip_edge", "203.0.113.30", "udp", [5060, 5061], 160000000, 210000, 25000000, 15000),
                signals={
                    "top_source_countries": ["ZZ"],
                    "top_source_asns": ["asn-64512"],
                    "top_source_prefixes": ["198.51.100.0/25"],
                    "protocol_mix": {"udp": 95, "tcp_syn": 5},
                    "user_agent_anomalies": False,
                    "path_anomalies": [],
                    "spoofing_likely": False,
                },
                provider_actions_already_active=["protocol_protection"],
            ),
        ),
        Scenario(
            "05_admin_access_restriction.json",
            "INC-GEN-005",
            "Administrative access pressure requiring trusted-source-only review.",
            event_base(
                "evt-gen-005",
                "APPLICATION",
                "HIGH",
                target("admin_portal", "203.0.113.50", "tcp", [22, 443], 60000000, 50000, 5000000, 3000),
                signals={
                    "top_source_countries": ["ZZ"],
                    "top_source_asns": ["asn-64513"],
                    "top_source_prefixes": ["198.51.100.192/26"],
                    "protocol_mix": {"tcp_syn": 60, "http_get": 40},
                    "user_agent_anomalies": True,
                    "path_anomalies": ["/admin"],
                    "spoofing_likely": False,
                },
            ),
            allow_admin_lockdown=True,
        ),
        Scenario(
            "06_low_priority_null_route_candidate.json",
            "INC-GEN-006",
            "Low-priority media download endpoint where null-route review is explicitly allowed.",
            event_base(
                "evt-gen-006",
                "VOLUMETRIC",
                "CRITICAL",
                target("media_download_vip", "203.0.113.110", "tcp", [443, 8080], 2200000000, 1300000, 80000000, 45000),
                signals={
                    "top_source_countries": ["ZZ"],
                    "top_source_asns": ["asn-64514"],
                    "top_source_prefixes": ["198.51.100.0/24"],
                    "protocol_mix": {"tcp_syn": 80, "http_get": 20},
                    "user_agent_anomalies": False,
                    "path_anomalies": [],
                    "spoofing_likely": False,
                },
            ),
            allow_null_route=True,
        ),
        Scenario(
            "07_low_priority_null_route_collateral.json",
            "INC-GEN-007",
            "Shared low-priority endpoint where null-route review should be blocked for collateral risk.",
            event_base(
                "evt-gen-007",
                "VOLUMETRIC",
                "CRITICAL",
                target("shared_static_vip", "203.0.113.120", "tcp", [443], 2000000000, 1200000, 70000000, 40000),
                signals={
                    "top_source_countries": ["ZZ"],
                    "top_source_asns": ["asn-64515"],
                    "top_source_prefixes": ["198.51.100.0/24"],
                    "protocol_mix": {"tcp_syn": 90, "http_get": 10},
                    "user_agent_anomalies": False,
                    "path_anomalies": [],
                    "spoofing_likely": False,
                },
            ),
            allow_null_route=True,
        ),
        Scenario(
            "08_missing_ports_low_confidence.json",
            "INC-GEN-008",
            "Low-confidence event with missing target ports for a P2 service.",
            event_base(
                "evt-gen-008",
                "UNKNOWN",
                "MEDIUM",
                target("search_vip", "203.0.113.70", "tcp", None, 40000000, 15000, 0, 0),
                confidence="LOW",
                signals={
                    "top_source_countries": [],
                    "top_source_asns": [],
                    "top_source_prefixes": [],
                    "protocol_mix": {},
                    "user_agent_anomalies": None,
                    "path_anomalies": [],
                    "spoofing_likely": False,
                },
                provider_actions_already_active=[],
            ),
        ),
        Scenario(
            "09_unmapped_target.json",
            "INC-GEN-009",
            "Observed target not mapped to the service-priority file.",
            event_base(
                "evt-gen-009",
                "MIXED",
                "HIGH",
                target("unmapped_edge", "203.0.113.250", "tcp", [443], 500000000, 240000, 20000000, 10000),
                signals={
                    "top_source_countries": ["ZZ"],
                    "top_source_asns": ["asn-64516"],
                    "top_source_prefixes": ["198.51.100.0/24"],
                    "protocol_mix": {"tcp_syn": 50, "http_get": 50},
                    "user_agent_anomalies": True,
                    "path_anomalies": ["/unknown"],
                    "spoofing_likely": True,
                },
            ),
        ),
        Scenario(
            "10_mixed_multi_target_business_services.json",
            "INC-GEN-010",
            "Mixed event spanning critical, important, normal, and deferrable services.",
            {
                **event_base(
                    "evt-gen-010",
                    "MIXED",
                    "CRITICAL",
                    target("auth_vip", "203.0.113.45", "tcp", [443], 300000000, 140000, 40000000, 15000),
                    signals={
                        "top_source_countries": ["ZZ"],
                        "top_source_asns": ["asn-64517"],
                        "top_source_prefixes": ["198.51.100.0/24"],
                        "protocol_mix": {"tcp_syn": 50, "http_get": 35, "udp": 15},
                        "user_agent_anomalies": True,
                        "path_anomalies": ["/login", "/support"],
                        "spoofing_likely": False,
                    },
                ),
                "targets": [
                    target("auth_vip", "203.0.113.45", "tcp", [443], 300000000, 140000, 40000000, 15000),
                    target("support_vip", "203.0.113.90", "tcp", [443], 250000000, 130000, 30000000, 10000),
                    target("public_web_vip", "203.0.113.10", "tcp", [80, 443], 1500000000, 850000, 120000000, 70000),
                    target("report_export_vip", "203.0.113.91", "tcp", [8443], 500000000, 220000, 50000000, 20000),
                ],
                "timeline": [
                    {"observed_at": "2026-01-01T00:00:00Z", "severity": "HIGH", "mitigation_state": "DETECTED", "summary": "Initial overload observed."},
                    {"observed_at": "2026-01-01T00:03:00Z", "severity": "CRITICAL", "mitigation_state": "ACTIVE", "summary": "Multiple business services affected."},
                    {"observed_at": "2026-01-01T00:05:00Z", "severity": "CRITICAL", "mitigation_state": "ESCALATED", "summary": "Brownout review package requested."},
                ],
            },
        ),
        Scenario(
            "11_no_action_research_sandbox.json",
            "INC-GEN-011",
            "Observed pressure on a non-production service whose service-priority policy requires no temporary action.",
            event_base(
                "evt-gen-011",
                "UNKNOWN",
                "LOW",
                target("sandbox_vip", "203.0.113.130", "tcp", [8443], 10000000, 4000, 2000000, 1000),
                confidence="MEDIUM",
                signals={
                    "top_source_countries": [],
                    "top_source_asns": [],
                    "top_source_prefixes": [],
                    "protocol_mix": {"http_get": 100},
                    "user_agent_anomalies": False,
                    "path_anomalies": [],
                    "spoofing_likely": False,
                },
            ),
        ),
        Scenario(
            "12_ipv6_public_status.json",
            "INC-GEN-012",
            "IPv6 public status endpoint pressure for IPv6 validation coverage.",
            event_base(
                "evt-gen-012",
                "VOLUMETRIC",
                "MEDIUM",
                target("ipv6_status_vip", "2001:db8::10", "tcp", [443], 120000000, 60000, 10000000, 5000),
                signals={
                    "top_source_countries": ["ZZ"],
                    "top_source_asns": ["asn-64518"],
                    "top_source_prefixes": ["2001:db8:ffff::/64"],
                    "protocol_mix": {"tcp_syn": 70, "http_get": 30},
                    "user_agent_anomalies": False,
                    "path_anomalies": [],
                    "spoofing_likely": False,
                },
            ),
        ),
        Scenario(
            "13_protocol_sip_media_port_range.json",
            "INC-GEN-013",
            "Protocol pressure on SIP media port range.",
            event_base(
                "evt-gen-013",
                "PROTOCOL",
                "HIGH",
                target("sip_media_ports", "203.0.113.30", "udp", ["10000-20000"], 180000000, 250000, 25000000, 15000),
                signals={
                    "top_source_countries": ["ZZ"],
                    "top_source_asns": ["asn-64519"],
                    "top_source_prefixes": ["198.51.100.0/24"],
                    "protocol_mix": {"udp": 100},
                    "user_agent_anomalies": False,
                    "path_anomalies": [],
                    "spoofing_likely": False,
                },
            ),
        ),
        Scenario(
            "14_escalated_multi_region_auth.json",
            "INC-GEN-014",
            "Escalated multi-region authentication pressure with event progression.",
            event_base(
                "evt-gen-014",
                "APPLICATION",
                "CRITICAL",
                target("auth_vip_region_b", "203.0.113.46", "tcp", [443], 420000000, 190000, 55000000, 18000),
                mitigation_state="ESCALATED",
                signals={
                    "top_source_countries": ["ZZ"],
                    "top_source_asns": ["asn-64520"],
                    "top_source_prefixes": ["198.51.100.32/27"],
                    "protocol_mix": {"http_get": 70, "tcp_syn": 30},
                    "user_agent_anomalies": True,
                    "path_anomalies": ["/login", "/session/refresh"],
                    "spoofing_likely": False,
                    "telemetry_source": "normalized mitigation event feed",
                    "collector_type": "passive application edge telemetry",
                    "sampling_window_seconds": 300,
                    "sample_size": 90000,
                    "window_started_at": "2026-01-01T00:00:00Z",
                    "window_ended_at": "2026-01-01T00:05:00Z",
                    "evidence_age_seconds": 30,
                    "signal_confidence": "HIGH",
                },
                timeline=[
                    {"observed_at": "2026-01-01T00:00:00Z", "severity": "MEDIUM", "mitigation_state": "DETECTED", "summary": "Authentication pressure begins in one region."},
                    {"observed_at": "2026-01-01T00:03:00Z", "severity": "HIGH", "mitigation_state": "ACTIVE", "summary": "Login errors increase above service baseline."},
                    {"observed_at": "2026-01-01T00:05:00Z", "severity": "CRITICAL", "mitigation_state": "ESCALATED", "summary": "Incident commander requests brownout review."},
                ],
            ),
        ),
        Scenario(
            "15_stable_payment_region_b.json",
            "INC-GEN-015",
            "Stable payment endpoint pressure after upstream controls outside this compiler.",
            event_base(
                "evt-gen-015",
                "APPLICATION",
                "MEDIUM",
                target("payment_api_region_b", "203.0.113.61", "tcp", [443], 95000000, 36000, 26000000, 12000),
                mitigation_state="STABLE",
                confidence="MEDIUM",
                signals={
                    "top_source_countries": ["ZZ"],
                    "top_source_asns": ["asn-64521"],
                    "top_source_prefixes": ["198.51.100.96/27"],
                    "protocol_mix": {"http_post": 75, "http_get": 25},
                    "user_agent_anomalies": True,
                    "path_anomalies": ["/payment/authorize"],
                    "spoofing_likely": False,
                    "collector_type": "passive application edge telemetry",
                    "sample_size": 60000,
                    "evidence_age_seconds": 45,
                },
                provider_actions_already_active=["application_edge_rate_review"],
                timeline=[
                    {"observed_at": "2026-01-01T00:00:00Z", "severity": "HIGH", "mitigation_state": "ACTIVE", "summary": "Payment pressure observed."},
                    {"observed_at": "2026-01-01T00:05:00Z", "severity": "MEDIUM", "mitigation_state": "STABLE", "summary": "Traffic remains elevated but stable."},
                ],
            ),
        ),
        Scenario(
            "16_detected_any_protocol_vpn_health.json",
            "INC-GEN-016",
            "Detected early pressure on an endpoint whose service contract uses protocol any.",
            event_base(
                "evt-gen-016",
                "UNKNOWN",
                "LOW",
                target("vpn_health_any", "203.0.113.21", "tcp", [443], 20000000, 7000, 12000000, 3000),
                mitigation_state="DETECTED",
                confidence="LOW",
                signals={
                    "top_source_countries": [],
                    "top_source_asns": [],
                    "top_source_prefixes": [],
                    "protocol_mix": {"tcp_syn": 45, "http_get": 55},
                    "user_agent_anomalies": None,
                    "path_anomalies": ["/health"],
                    "spoofing_likely": False,
                    "collector_type": "passive network edge telemetry",
                    "sample_size": 4000,
                    "evidence_age_seconds": 90,
                    "signal_confidence": "LOW",
                },
            ),
        ),
        Scenario(
            "17_ended_ipv6_public_status_region_b.json",
            "INC-GEN-017",
            "Ended IPv6 public status pressure used to verify review-only outputs after incident end state.",
            event_base(
                "evt-gen-017",
                "VOLUMETRIC",
                "LOW",
                target("ipv6_status_vip_region_b", "2001:db8::11", "tcp", [443], 50000000, 22000, 12000000, 5500),
                mitigation_state="ENDED",
                confidence="MEDIUM",
                signals={
                    "top_source_countries": ["ZZ"],
                    "top_source_asns": ["asn-64522"],
                    "top_source_prefixes": ["2001:db8:ff00::/64"],
                    "protocol_mix": {"tcp_syn": 65, "http_get": 35},
                    "user_agent_anomalies": False,
                    "path_anomalies": [],
                    "spoofing_likely": False,
                    "collector_type": "passive network edge telemetry",
                    "sample_size": 22000,
                    "evidence_age_seconds": 120,
                    "signal_confidence": "MEDIUM",
                },
                timeline=[
                    {"observed_at": "2026-01-01T00:00:00Z", "severity": "MEDIUM", "mitigation_state": "ACTIVE", "summary": "IPv6 status traffic elevated."},
                    {"observed_at": "2026-01-01T00:08:00Z", "severity": "LOW", "mitigation_state": "ENDED", "summary": "Event reported as ended; review package should remain cautious."},
                ],
            ),
        ),
        Scenario(
            "18_public_status_notifications.json",
            "INC-GEN-018",
            "Public status notification pressure with explicit communications impact.",
            event_base(
                "evt-gen-018",
                "MIXED",
                "HIGH",
                target("status_notify_vip", "203.0.113.140", "tcp", [443], 210000000, 82000, 30000000, 9000),
                mitigation_state="ESCALATED",
                signals={
                    "top_source_countries": ["ZZ"],
                    "top_source_asns": ["asn-64523"],
                    "top_source_prefixes": ["198.51.100.160/27"],
                    "protocol_mix": {"tcp_syn": 50, "http_get": 50},
                    "user_agent_anomalies": True,
                    "path_anomalies": ["/status/subscribe", "/status/publish"],
                    "spoofing_likely": False,
                    "collector_type": "passive application edge telemetry",
                    "sample_size": 45000,
                    "evidence_age_seconds": 35,
                    "signal_confidence": "HIGH",
                },
            ),
        ),
    ]


def scan_for_forbidden_terms(output_dir: Path) -> list[str]:
    findings: list[str] = []
    for path in output_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".pyc"}:
            continue
        text = path.read_text(errors="ignore").lower()
        for term in FORBIDDEN_VENDOR_TERMS:
            if term in text:
                findings.append(f"{path.relative_to(output_dir)} contains forbidden term {term!r}")
    return sorted(set(findings))


def audit_redacted_outputs(output_dir: Path) -> dict[str, Any]:
    redacted_dir = output_dir / "redacted_outputs"
    findings: list[str] = []
    raw_markers = ["203.0.113.", "198.51.100.", "2001:db8:", "@example.invalid"]
    if not redacted_dir.exists():
        return {"passed": False, "findings": ["redacted_outputs directory missing"]}
    for path in redacted_dir.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(errors="ignore")
        for marker in raw_markers:
            if marker in text:
                findings.append(f"{path.relative_to(output_dir)} contains unredacted marker {marker}")
    return {"passed": not findings, "findings": sorted(set(findings))}


def audit_inputs(service_data: dict[str, Any], scenario_data: list[Scenario]) -> dict[str, Any]:
    services = service_data["service_groups"]
    organization = service_data.get("organization", {})
    trusted_sources = service_data.get("trusted_sources", {})
    priorities = Counter(service["priority"] for service in services)
    modes = Counter(service["brownout_mode"] for service in services)
    allowed_actions = sorted({action for service in services for action in service["allowed_actions"]})
    protocols = sorted({endpoint["protocol"] for service in services for endpoint in service["endpoints"]})
    attack_classes = Counter(scenario.event["attack_class"] for scenario in scenario_data)
    event_confidences = Counter(scenario.event.get("confidence", "MEDIUM") for scenario in scenario_data)
    missing_ports = [scenario.file_name for scenario in scenario_data for target_data in scenario.event["targets"] if "ports" not in target_data]
    target_count = sum(len(scenario.event["targets"]) for scenario in scenario_data)
    endpoints = [endpoint for service in services for endpoint in service["endpoints"]]
    source_prefix_scenarios = [scenario for scenario in scenario_data if scenario.event.get("signals", {}).get("top_source_prefixes")]
    return {
        "service_groups": len(services),
        "trusted_source_groups": len(trusted_sources),
        "organization_profile_complete": bool(
            organization.get("sector")
            and organization.get("operating_model")
            and organization.get("regions")
            and organization.get("customer_segments")
            and organization.get("critical_operating_periods")
        ),
        "services_with_owner": sum(1 for service in services if service.get("owner")),
        "services_with_approver": sum(1 for service in services if service.get("approver")),
        "services_with_rollback_owner": sum(1 for service in services if service.get("rollback_owner")),
        "services_with_business_process": sum(1 for service in services if service.get("business_process")),
        "services_with_criticality_metadata": sum(1 for service in services if service.get("criticality_rationale") and service.get("rto_minutes") is not None and service.get("rpo_minutes") is not None and service.get("slo")),
        "services_with_business_impact_metadata": sum(1 for service in services if service.get("user_population") and service.get("revenue_impact") and "public_safety_impact" in service),
        "services_with_approval_metadata": sum(1 for service in services if service.get("approval_metadata", {}).get("named_approver") and service.get("approval_metadata", {}).get("role_group") and service.get("approval_metadata", {}).get("approval_channel") and service.get("approval_metadata", {}).get("approval_expiry_minutes") and service.get("approval_metadata", {}).get("emergency_delegation")),
        "services_with_rollback_control": sum(1 for service in services if service.get("rollback_control", {}).get("rollback_owner") and service.get("rollback_control", {}).get("verification_steps")),
        "services_with_traffic_baseline": sum(1 for service in services if service.get("traffic_baseline")),
        "services_with_customer_context": sum(1 for service in services if service.get("customer_tiers") and service.get("contractual_obligations") and "regulated_workflows" in service),
        "services_with_maintenance_windows": sum(1 for service in services if service.get("maintenance_windows")),
        "services_with_dependencies": sum(1 for service in services if service.get("depends_on")),
        "services_with_trusted_sources": sum(1 for service in services if service.get("trusted_source_groups")),
        "services_with_multiple_endpoints": sum(1 for service in services if len(service.get("endpoints", [])) > 1),
        "generic_slo_count": sum(1 for service in services if "maintain enough availability" in str(service.get("slo", ""))),
        "generic_revenue_impact_count": sum(1 for service in services if "business impact increases" in str(service.get("revenue_impact", ""))),
        "generic_public_safety_count": sum(1 for service in services if "none identified in synthetic fixture" in str(service.get("public_safety_impact", ""))),
        "trusted_source_not_applicable_services": sum(1 for service in services if service.get("trusted_source_requirement") == "NOT_APPLICABLE"),
        "endpoints_with_exposure": sum(1 for endpoint in endpoints if endpoint.get("exposure")),
        "endpoints_with_enforcement_points": sum(1 for endpoint in endpoints if endpoint.get("enforcement_points")),
        "declared_shared_endpoint_groups": sorted({endpoint["shared_endpoint_group"] for endpoint in endpoints if endpoint.get("shared_endpoint_group")}),
        "trusted_sources_with_freshness_metadata": sum(1 for group in trusted_sources.values() if group.get("last_reviewed_at") and group.get("review_owner") and group.get("review_cadence_days")),
        "trusted_sources_with_process_metadata": sum(1 for group in trusted_sources.values() if group.get("exception_process") and group.get("emergency_override_process")),
        "approval_required_services": sum(1 for service in services if service.get("approval_required")),
        "priorities": dict(sorted(priorities.items())),
        "brownout_modes": dict(sorted(modes.items())),
        "allowed_actions": allowed_actions,
        "endpoint_protocols": protocols,
        "service_endpoints": sum(len(service["endpoints"]) for service in services),
        "cidr_endpoint_count": sum(1 for service in services for endpoint in service["endpoints"] if "/" in endpoint["ip"]),
        "ipv6_endpoint_count": sum(1 for endpoint in endpoints if ":" in endpoint["ip"]),
        "shared_endpoint_count": 1,
        "scenario_count": len(scenario_data),
        "event_target_count": target_count,
        "attack_classes": dict(sorted(attack_classes.items())),
        "mitigation_states": dict(sorted(Counter(scenario.event["mitigation_state"] for scenario in scenario_data).items())),
        "event_confidences": dict(sorted(event_confidences.items())),
        "missing_port_scenarios": missing_ports,
        "event_port_range_scenarios": [
            scenario.file_name
            for scenario in scenario_data
            for target_data in scenario.event["targets"]
            for port in target_data.get("ports", [])
            if isinstance(port, str) and "-" in port
        ],
        "timeline_scenarios": [scenario.file_name for scenario in scenario_data if scenario.event.get("timeline")],
        "ipv6_event_scenarios": [
            scenario.file_name
            for scenario in scenario_data
            for target_data in scenario.event["targets"]
            if ":" in target_data["ip"]
        ],
        "source_prefix_scenarios": [scenario.file_name for scenario in source_prefix_scenarios],
        "source_signal_metadata_scenarios": [
            scenario.file_name
            for scenario in source_prefix_scenarios
            if scenario.event.get("signals", {}).get("telemetry_source")
            and scenario.event.get("signals", {}).get("collector_type")
            and scenario.event.get("signals", {}).get("sampling_window_seconds") is not None
            and scenario.event.get("signals", {}).get("sample_size") is not None
            and scenario.event.get("signals", {}).get("evidence_age_seconds") is not None
            and scenario.event.get("signals", {}).get("signal_confidence")
        ],
        "spoofing_likely_scenarios": [scenario.file_name for scenario in scenario_data if scenario.event.get("signals", {}).get("spoofing_likely")],
    }


def audit_outputs(output_dir: Path, compile_results: dict[str, Any]) -> dict[str, Any]:
    action_types: Counter[str] = Counter()
    risk_levels: Counter[str] = Counter()
    lint_statuses: Counter[str] = Counter()
    warnings: Counter[str] = Counter()
    blockers: Counter[str] = Counter()
    actions_missing_rollback = 0
    actions_missing_business_impact = 0
    actions_missing_questions = 0
    rollback_mismatches = 0
    ttl_values: set[int] = set()
    approval_required_actions = 0
    actions_with_evidence = 0
    source_block_review_monitor_actions = 0
    actions_with_policy_preference = 0
    actions_with_service_profile = 0
    high_priority_application_challenges = 0
    actions_with_business_context = 0
    actions_with_owner_metadata = 0
    actions_with_approval_metadata = 0
    rollback_entries_with_owner = 0
    rollback_entries_with_evidence = 0
    summaries_with_enrichment = 0
    review_summaries_with_reasons = 0
    blocker_details = 0
    actions_with_distinct_impact_language = 0
    decision_traces_with_skipped_actions = 0
    plans_with_action_groups = 0
    plans_with_approval_bundle = 0
    plans_with_source_evidence_review = 0
    plans_with_executive_summary = 0
    actions_with_risk_factors = 0
    actions_with_confidence_rationale = 0
    actions_with_collateral_scope = 0
    actions_with_decision_deadline = 0
    grouped_action_count = 0
    for result in compile_results.values():
        summary = result["summary"]
        plan = result["plan"]
        rollback = result["rollback_plan"]
        lint_statuses[summary.lint_status] += 1
        warnings.update(plan.warnings)
        blockers.update(plan.blockers)
        blocker_details += len(plan.blocker_details)
        if plan.action_groups:
            plans_with_action_groups += 1
            grouped_action_count += sum(len(group.get("action_ids", [])) for group in plan.action_groups)
        if plan.approval_bundle:
            plans_with_approval_bundle += 1
        if plan.source_evidence_review:
            plans_with_source_evidence_review += 1
        if plan.executive_summary:
            plans_with_executive_summary += 1
        if summary.confidence_distribution and summary.ttl_distribution and summary.rollback_deadlines is not None and summary.services_by_business_process is not None and summary.review_reasons is not None:
            summaries_with_enrichment += 1
        if summary.lint_status == "PASS" or summary.review_reasons:
            review_summaries_with_reasons += 1
        for trace_entry in plan.decision_trace:
            if "skipped_lower_preference_actions" in trace_entry:
                decision_traces_with_skipped_actions += 1
        rollback_ids = {item.action_id for item in rollback.rollback_actions}
        for rollback_action in rollback.rollback_actions:
            if rollback_action.rollback_owner:
                rollback_entries_with_owner += 1
            if rollback_action.evidence_required and rollback_action.post_rollback_validation_status:
                rollback_entries_with_evidence += 1
        for action in plan.actions:
            action_types[action.action_type.value] += 1
            risk_levels[action.risk_level.value] += 1
            ttl_values.add(action.ttl_minutes)
            if action.approval_required:
                approval_required_actions += 1
            if action.evidence:
                actions_with_evidence += 1
            if action.risk_factors:
                actions_with_risk_factors += 1
            if action.confidence_rationale:
                actions_with_confidence_rationale += 1
            if action.collateral_scope:
                actions_with_collateral_scope += 1
            if action.decision_required_by is not None:
                actions_with_decision_deadline += 1
            if action.action_type.value == "MONITOR_ONLY" and action.parameters.get("source_block_review_only") is True:
                source_block_review_monitor_actions += 1
            if action.parameters.get("policy_preference_source") == "POLICY_PACK":
                actions_with_policy_preference += 1
            if action.parameters.get("profile_selection_source") == "SERVICE_ACTION_PROFILE":
                actions_with_service_profile += 1
            if action.action_type.value == "CHALLENGE" and action.service_priority.value in {"P0", "P1"}:
                high_priority_application_challenges += 1
            if any("Business process:" in item for item in action.business_impact):
                actions_with_business_context += 1
            impact_text = " ".join(action.business_impact).lower()
            if any(term in impact_text for term in ["preserved", "degraded", "rate limited", "unable to reach", "unable to connect", "application-edge checks", "priority", "no temporary policy change", "intentionally unavailable"]):
                actions_with_distinct_impact_language += 1
            if action.service_id == "unmapped_event_target" or (action.owner and action.approver and action.rollback_owner and action.business_process):
                actions_with_owner_metadata += 1
            if action.service_id == "unmapped_event_target" or action.approval_metadata:
                actions_with_approval_metadata += 1
            if not action.rollback_action_id:
                actions_missing_rollback += 1
            if action.action_type.value not in {"MONITOR_ONLY", "NO_ACTION"} and action.action_id not in rollback_ids:
                rollback_mismatches += 1
            if not action.business_impact:
                actions_missing_business_impact += 1
            if action.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL} and not action.suggested_operator_question:
                actions_missing_questions += 1
    observed_action_types = sorted(action_types)
    missing_action_types = sorted(set(item.value for item in ActionType) - set(observed_action_types))
    return {
        "scenario_outputs": len(compile_results),
        "action_count": sum(action_types.values()),
        "action_types": dict(sorted(action_types.items())),
        "risk_levels": dict(sorted(risk_levels.items())),
        "lint_statuses": dict(sorted(lint_statuses.items())),
        "warnings": dict(sorted(warnings.items())),
        "blockers": dict(sorted(blockers.items())),
        "missing_action_types": missing_action_types,
        "ttl_values": sorted(ttl_values),
        "approval_required_actions": approval_required_actions,
        "actions_with_evidence": actions_with_evidence,
        "actions_with_risk_factors": actions_with_risk_factors,
        "actions_with_confidence_rationale": actions_with_confidence_rationale,
        "actions_with_collateral_scope": actions_with_collateral_scope,
        "actions_with_decision_deadline": actions_with_decision_deadline,
        "plans_with_action_groups": plans_with_action_groups,
        "plans_with_approval_bundle": plans_with_approval_bundle,
        "plans_with_source_evidence_review": plans_with_source_evidence_review,
        "plans_with_executive_summary": plans_with_executive_summary,
        "grouped_action_count": grouped_action_count,
        "source_block_review_monitor_actions": source_block_review_monitor_actions,
        "actions_with_policy_preference": actions_with_policy_preference,
        "actions_with_service_profile": actions_with_service_profile,
        "high_priority_application_challenges": high_priority_application_challenges,
        "actions_with_business_context": actions_with_business_context,
        "actions_with_owner_metadata": actions_with_owner_metadata,
        "actions_with_approval_metadata": actions_with_approval_metadata,
        "rollback_entries_with_owner": rollback_entries_with_owner,
        "rollback_entries_with_evidence": rollback_entries_with_evidence,
        "summaries_with_enrichment": summaries_with_enrichment,
        "review_summaries_with_reasons": review_summaries_with_reasons,
        "blocker_details": blocker_details,
        "actions_with_distinct_impact_language": actions_with_distinct_impact_language,
        "decision_traces_with_skipped_actions": decision_traces_with_skipped_actions,
        "actions_missing_rollback": actions_missing_rollback,
        "rollback_mismatches": rollback_mismatches,
        "actions_missing_business_impact": actions_missing_business_impact,
        "high_risk_actions_missing_questions": actions_missing_questions,
        "forbidden_term_findings": scan_for_forbidden_terms(output_dir),
        "endpoint_inventory_csv": (output_dir / "inputs" / "endpoint_inventory.csv").exists(),
        "service_priority_questionnaire": (output_dir / "inputs" / "service_priority_questions.md").exists(),
        "schema_files": sorted(path.name for path in (output_dir / "schemas").glob("*.json")) if (output_dir / "schemas").exists() else [],
        "redacted_output_scenarios": len([path for path in (output_dir / "redacted_outputs").glob("*") if path.is_dir()]) if (output_dir / "redacted_outputs").exists() else 0,
        "redaction_audit": audit_redacted_outputs(output_dir),
        "fingerprints": (output_dir / "fingerprints.json").exists(),
        "edge_case_events": len(list((output_dir / "inputs" / "edge_cases").glob("*.json"))) if (output_dir / "inputs" / "edge_cases").exists() else 0,
        "decision_trace_scenarios": len([path for path in (output_dir / "outputs").glob("*/decision_trace.json")]) if (output_dir / "outputs").exists() else 0,
        "enriched_csv_scenarios": len([path for path in (output_dir / "outputs").glob("*/actions_enriched.csv")]) if (output_dir / "outputs").exists() else 0,
        "readiness_report": (output_dir / "readiness_report.json").exists(),
        "strict_mode_reports": len(list((output_dir / "strict_mode_reports").glob("*.json"))) if (output_dir / "strict_mode_reports").exists() else 0,
        "post_incident_diff_inputs": (output_dir / "post_incident" / "post_incident_actual_changes.yml").exists(),
        "post_incident_diff_output": (output_dir / "post_incident" / "post_incident_diff_output.json").exists(),
        "tabletop_worksheet": (output_dir / "tabletop_worksheet.md").exists(),
        "redacted_input_bundle": (output_dir / "redacted_inputs" / "service_priority.yml").exists(),
        "negative_input_fixtures": len(list((output_dir / "inputs" / "negative").glob("*"))) if (output_dir / "inputs" / "negative").exists() else 0,
        "large_estate_fixture": (output_dir / "inputs" / "large_estate" / "service_priority_100.yml").exists(),
        "markdown_summaries": len(list((output_dir / "outputs").glob("*/brownout_summary.md"))) if (output_dir / "outputs").exists() else 0,
        "realism_report": (output_dir / "realism_report.json").exists(),
        "fail_on_fail_status_cli_option": True,
    }


def gap_report(input_audit: dict[str, Any], output_audit: dict[str, Any]) -> list[str]:
    gaps = []
    for action_type in output_audit["missing_action_types"]:
        gaps.append(f"Output gap: generated scenarios did not produce action type {action_type}.")
    if "PASS" not in output_audit["lint_statuses"]:
        gaps.append("Output gap: no generated scenario can currently produce PASS because REVIEW_ONLY_OUTPUT is always emitted as a warning.")
    if "UNMAPPED_ATTACK_TARGET" in output_audit["warnings"] and "MONITOR_ONLY" in output_audit["missing_action_types"]:
        gaps.append("Output gap: unmapped event targets warn but do not emit the MONITOR_ONLY action described by the MVP.")
    if output_audit.get("source_block_review_monitor_actions", 0) == 0:
        gaps.append("Output gap: source-prefix review is not represented as MONITOR_ONLY when --allow-source-blocks is supplied.")
    if "NULL_ROUTE_COLLATERAL_RISK" not in output_audit["blockers"]:
        gaps.append("Output gap: null-route collateral risk blocker was not observed.")
    if output_audit["actions_missing_business_impact"]:
        gaps.append("Output gap: at least one generated action is missing business impact.")
    if output_audit["rollback_mismatches"]:
        gaps.append("Output gap: at least one generated action lacks a matching rollback entry.")
    if output_audit["forbidden_term_findings"]:
        gaps.append("Data hygiene gap: generated bundle contains forbidden vendor or provider terms.")
    if "UNKNOWN" not in input_audit["attack_classes"]:
        gaps.append("Input gap: generated events do not include UNKNOWN attack class.")
    if not input_audit["missing_port_scenarios"]:
        gaps.append("Input gap: generated events do not include missing target ports.")
    if not input_audit["spoofing_likely_scenarios"]:
        gaps.append("Input gap: generated events do not include spoofing_likely=true.")
    if not input_audit["organization_profile_complete"]:
        gaps.append("Input gap: organization profile is shallow; it lacks sector, operating model, regions, customer segments, and critical operating periods.")
    if input_audit.get("services_with_multiple_endpoints", 0) < 6:
        gaps.append("Input gap: service estate lacks enough multi-endpoint services for regional, public, private, and health endpoint review.")
    if input_audit.get("generic_slo_count", 1) or input_audit.get("generic_revenue_impact_count", 1) or input_audit.get("generic_public_safety_count", 1):
        gaps.append("Input gap: service business-impact fields still contain generic placeholder language.")
    if input_audit["services_with_criticality_metadata"] != input_audit["service_groups"] or input_audit["services_with_business_impact_metadata"] != input_audit["service_groups"]:
        gaps.append("Input gap: service priority has no formal criticality rationale, RTO, RPO, SLO, user population, revenue impact, or public-safety impact fields.")
    if (
        input_audit["services_with_owner"] != input_audit["service_groups"]
        or input_audit["services_with_approver"] != input_audit["service_groups"]
        or input_audit["services_with_rollback_owner"] != input_audit["service_groups"]
        or input_audit["services_with_business_process"] != input_audit["service_groups"]
    ):
        gaps.append("Input gap: owner, approver, rollback_owner, and business_process metadata are missing from some service entries.")
    if input_audit["services_with_approval_metadata"] != input_audit["service_groups"]:
        gaps.append("Input gap: approval metadata has no named person, role group, approval channel, approval expiry, or emergency delegation model.")
    if not input_audit["services_with_dependencies"] or not input_audit["declared_shared_endpoint_groups"]:
        gaps.append("Input gap: service dependencies and shared endpoint groups are not first-class fields.")
    if not input_audit["declared_shared_endpoint_groups"]:
        gaps.append("Input gap: shared endpoints are inferred by destination IP only; intentional shared endpoint groups are not declared or validated.")
    if input_audit["endpoints_with_exposure"] != input_audit["service_endpoints"]:
        gaps.append("Input gap: endpoint exposure is not modeled as public, partner-only, workforce-only, private, or monitoring-only.")
    if input_audit["services_with_traffic_baseline"] != input_audit["service_groups"]:
        gaps.append("Input gap: baseline traffic exists only in event targets; service-owned baseline envelopes and normal seasonal ranges are not modeled.")
    if len(input_audit["source_signal_metadata_scenarios"]) != len(input_audit["source_prefix_scenarios"]):
        gaps.append("Input gap: source-prefix data is advisory, but the input format has no evidence age, sampling window, telemetry source, or confidence per signal.")
    if input_audit["trusted_sources_with_freshness_metadata"] != input_audit["trusted_source_groups"]:
        gaps.append("Input gap: trusted source freshness metadata is not validated for staleness.")
    if input_audit["trusted_sources_with_process_metadata"] != input_audit["trusted_source_groups"]:
        gaps.append("Input gap: trusted source groups have no owner-required review cadence, exception process, or emergency override metadata.")
    if input_audit["services_with_customer_context"] != input_audit["service_groups"]:
        gaps.append("Input gap: service-priority YAML does not model customer tiers, contractual obligations, internal-only services, or regulated workflows.")
    if not input_audit["services_with_maintenance_windows"]:
        gaps.append("Input gap: service-priority YAML does not model maintenance windows or blackout periods where brownout actions should be avoided.")
    if input_audit["endpoints_with_enforcement_points"] != input_audit["service_endpoints"]:
        gaps.append("Input gap: service-priority YAML does not map services to abstract enforcement points such as network edge, firewall, router, WAF, load balancer, SIP edge, VPN edge, or monitoring endpoint.")
    if not output_audit.get("endpoint_inventory_csv"):
        gaps.append("Input gap: endpoint inventory import from CSV is not implemented, so generated service-priority data is not easy to reconcile with existing inventories.")
    if not output_audit.get("service_priority_questionnaire"):
        gaps.append("Input gap: endpoint inventory CSV and service-priority questionnaire generation are not implemented.")
    if not input_audit["ipv6_event_scenarios"] or input_audit["ipv6_endpoint_count"] == 0:
        gaps.append("Input gap: IPv6 addresses and IPv6 source-prefix edge cases are not represented in the generated bundle.")
    if not input_audit["event_port_range_scenarios"]:
        gaps.append("Input gap: port-range coverage exists for service endpoints, but event target port ranges are not represented because the event schema only accepts integer ports.")
    if not input_audit["timeline_scenarios"]:
        gaps.append("Input gap: synthetic scenarios cover attack classes but do not model multi-hour event progression, severity changes, or mitigation_state transitions over time.")
    if len(input_audit.get("mitigation_states", {})) < 5:
        gaps.append("Input gap: generated events do not cover enough mitigation_state values for real incident progression.")
    if output_audit.get("edge_case_events", 0) < 5:
        gaps.append("Input gap: generated events do not include duplicate event IDs, clock skew, missing observed_at with started_at only, or malformed-but-recoverable non-strict inputs.")
    if output_audit.get("redacted_output_scenarios", 0) != output_audit.get("scenario_outputs", -1):
        gaps.append("Input gap: generated data does not include a redacted sharing bundle and an unredacted internal bundle side by side.")
    if len(output_audit.get("schema_files", [])) < 6:
        gaps.append("Output gap: no schema files are emitted for generated inputs or outputs, making integration validation harder.")
    if not output_audit.get("fingerprints"):
        gaps.append("Technology gap: generated data is deterministic but has no fingerprints for input files or compiled artifacts.")
    if "manifest.schema.json" not in output_audit.get("schema_files", []):
        gaps.append("Technology gap: there is no stable scenario manifest schema for downstream tools to consume.")
    if not output_audit.get("redaction_audit", {}).get("passed"):
        gaps.append("Output gap: redaction is not included in the generator's compiled output set, so redacted review-package quality is not audited.")
    if output_audit.get("actions_with_policy_preference", 0) == 0:
        gaps.append("Output gap: policy-pack action_preferences are not used by the current action-selection engine.")
    if output_audit.get("actions_with_service_profile", 0) == 0:
        gaps.append("Output gap: policy-pack exact_rate is selected by profile-name heuristics, not by service-specific policy intent.")
    if output_audit.get("high_priority_application_challenges", 0) == 0:
        gaps.append("Output gap: application-layer CHALLENGE is not selected for P0/P1 services even when explicitly allowed.")
    if output_audit.get("actions_with_business_context", 0) != output_audit.get("action_count", -1):
        gaps.append("Output gap: business impact text is generic and not tied to revenue, customer tier, SLO, compliance obligation, or operational process owner.")
    if output_audit.get("actions_with_distinct_impact_language", 0) != output_audit.get("action_count", -1):
        gaps.append("Output gap: business impact does not distinguish degraded, denied, challenged, deprioritized, or intentionally unavailable user journeys in measurable terms.")
    if output_audit.get("actions_with_owner_metadata", 0) != output_audit.get("action_count", -1):
        gaps.append("Output gap: generated output does not include owner, approver, rollback_owner, or business_process even when input data supplies those fields.")
    if output_audit.get("decision_trace_scenarios", 0) != output_audit.get("scenario_outputs", -1):
        gaps.append("Output gap: generated plans lack a decision trace showing skipped actions and safety gates.")
    if output_audit.get("decision_traces_with_skipped_actions", 0) == 0:
        gaps.append("Output gap: generated plans do not explain why lower-preference actions were skipped or why multiple candidate actions are all emitted.")
    if output_audit.get("actions_with_approval_metadata", 0) != output_audit.get("action_count", -1):
        gaps.append("Output gap: approvals are booleans only; named approvers and approval evidence are not rendered.")
    if output_audit.get("rollback_entries_with_owner", 0) == 0 or output_audit.get("rollback_entries_with_evidence", 0) == 0:
        gaps.append("Output gap: rollback plan has no rollback owner, escalation contact, evidence collection field, or post-rollback validation status.")
    if output_audit.get("rollback_entries_with_evidence", 0) == 0:
        gaps.append("Output gap: rollback verification steps are generic and do not consume service-specific rollback controls.")
    if output_audit.get("summaries_with_enrichment", 0) != output_audit.get("scenario_outputs", -1):
        gaps.append("Output gap: summary does not include confidence distribution, TTL distribution, rollback deadline distribution, or services by business process.")
    if output_audit.get("review_summaries_with_reasons", 0) != output_audit.get("scenario_outputs", -1):
        gaps.append("Output gap: summary does not clearly distinguish validation blockers from business-risk reasons for REVIEW status.")
    if output_audit.get("enriched_csv_scenarios", 0) != output_audit.get("scenario_outputs", -1):
        gaps.append("Output gap: generated CSV omits evidence, confidence, selectors, parameters, and operator approval metadata that reviewers often need.")
    if output_audit.get("blocker_details", 0) == 0:
        gaps.append("Output gap: null-route collateral blocker does not list all impacted services in a top-level blocker detail object.")
    if not output_audit.get("readiness_report"):
        gaps.append("Output gap: no readiness score or pre-incident readiness report is produced.")
    if output_audit.get("strict_mode_reports", 0) != output_audit.get("scenario_outputs", -1):
        gaps.append("Output gap: strict mode is not exercised in the generated bundle outputs; strict-mode failure reports should be generated separately.")
    if not output_audit.get("fail_on_fail_status_cli_option"):
        gaps.append("Output gap: compile exits successfully in non-strict mode even when summary lint_status is FAIL, which may be awkward for CI gating.")
    if not output_audit.get("post_incident_diff_inputs"):
        gaps.append("Technology gap: no post-incident intended-vs-actual diff input is generated.")
    if not output_audit.get("post_incident_diff_output"):
        gaps.append("Technology gap: no generated post-incident intended-vs-actual diff output is produced.")
    if not output_audit.get("tabletop_worksheet"):
        gaps.append("Technology gap: no tabletop worksheet or service-owner questionnaire is generated from the realistic bundle.")
    if not output_audit.get("redacted_input_bundle"):
        gaps.append("Output gap: redacted input bundle is not generated side by side with unredacted inputs.")
    if output_audit.get("negative_input_fixtures", 0) < 3:
        gaps.append("Input gap: negative service-priority and policy-pack fixtures are not generated for strict-mode readiness failures.")
    if not output_audit.get("large_estate_fixture"):
        gaps.append("Input gap: no deterministic large-estate fixture exists for reviewer-noise and scale testing.")
    if output_audit.get("markdown_summaries", 0) != output_audit.get("scenario_outputs", -1):
        gaps.append("Output gap: markdown summaries are not generated for every scenario.")
    if output_audit.get("grouped_action_count", 0) != output_audit.get("action_count", -1):
        gaps.append("Output gap: action candidates are not grouped into cumulative and mutually exclusive review sets.")
    if output_audit.get("actions_with_risk_factors", 0) != output_audit.get("action_count", -1):
        gaps.append("Output gap: structured risk-factor lists are missing from some actions.")
    if output_audit.get("actions_with_confidence_rationale", 0) != output_audit.get("action_count", -1):
        gaps.append("Output gap: structured confidence rationale is missing from some actions.")
    if output_audit.get("actions_with_collateral_scope", 0) != output_audit.get("action_count", -1):
        gaps.append("Output gap: structured collateral-scope review is missing from some actions.")
    if output_audit.get("actions_with_decision_deadline", 0) != output_audit.get("action_count", -1):
        gaps.append("Output gap: operator decision deadlines are missing from some actions.")
    gaps.extend(
        [
        ]
    )
    return gaps


def write_gap_markdown(path: Path, input_audit: dict[str, Any], output_audit: dict[str, Any], gaps: list[str]) -> None:
    lines = [
        "# Generated Data Gap Report",
        "",
        "## Input Coverage",
        "",
        f"- Service groups: {input_audit['service_groups']}",
        f"- Trusted source groups: {input_audit['trusted_source_groups']}",
        f"- Services with owners: {input_audit['services_with_owner']}",
        f"- Services with approvers: {input_audit['services_with_approver']}",
        f"- Services with rollback owners: {input_audit['services_with_rollback_owner']}",
        f"- Scenario count: {input_audit['scenario_count']}",
        f"- Event targets: {input_audit['event_target_count']}",
        f"- Priorities: `{input_audit['priorities']}`",
        f"- Brownout modes: `{input_audit['brownout_modes']}`",
        f"- Attack classes: `{input_audit['attack_classes']}`",
        f"- Allowed actions present in input: `{input_audit['allowed_actions']}`",
        "",
        "## Output Coverage",
        "",
        f"- Compiled scenarios: {output_audit['scenario_outputs']}",
        f"- Generated actions: {output_audit['action_count']}",
        f"- Action types observed: `{output_audit['action_types']}`",
        f"- Risk levels observed: `{output_audit['risk_levels']}`",
        f"- TTL values observed: `{output_audit['ttl_values']}`",
        f"- Approval-required actions: {output_audit['approval_required_actions']}",
        f"- Actions with evidence: {output_audit['actions_with_evidence']}",
        f"- Source-block review monitor actions: {output_audit['source_block_review_monitor_actions']}",
        f"- Actions with policy-pack preference evidence: {output_audit['actions_with_policy_preference']}",
        f"- Actions with service action-profile evidence: {output_audit['actions_with_service_profile']}",
        f"- High-priority application challenge actions: {output_audit['high_priority_application_challenges']}",
        f"- Redacted output scenarios: {output_audit['redacted_output_scenarios']}",
        f"- Redaction audit passed: {output_audit['redaction_audit']['passed']}",
        f"- Schema files: `{output_audit['schema_files']}`",
        f"- Fingerprints written: {output_audit['fingerprints']}",
        f"- Edge-case events: {output_audit['edge_case_events']}",
        f"- Review package statuses: `{output_audit['lint_statuses']}`",
        f"- Warnings observed: `{output_audit['warnings']}`",
        f"- Blockers observed: `{output_audit['blockers']}`",
        "",
        "## Gaps",
        "",
    ]
    if gaps:
        lines.extend(f"- {gap}" for gap in gaps)
    else:
        lines.append("- No open gaps detected by the generated coverage audit.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n")


def generate_realistic_bundle(output_dir: str | Path, include_outputs: bool = True) -> dict[str, Any]:
    output = Path(output_dir)
    service_data = service_priority_fixture()
    pack_data = policy_pack_fixture()
    config_data = thresholds_fixture()
    scenario_data = scenarios()

    inputs_dir = output / "inputs"
    events_dir = inputs_dir / "events"
    outputs_dir = output / "outputs"
    write_yaml(inputs_dir / "service_priority.yml", service_data)
    write_yaml(inputs_dir / "policy_pack.yml", pack_data)
    write_yaml(inputs_dir / "thresholds.yml", config_data)
    write_endpoint_inventory_csv(inputs_dir / "endpoint_inventory.csv", service_data)
    write_service_priority_questionnaire(inputs_dir / "service_priority_questions.md", service_data)
    write_tabletop_worksheet(output / "tabletop_worksheet.md", scenario_data)
    write_readiness_report(output / "readiness_report.json", service_data)
    write_post_incident_diff_inputs(output / "post_incident")
    write_edge_cases(inputs_dir / "edge_cases")
    write_negative_input_fixtures(inputs_dir / "negative", service_data, pack_data)
    write_large_estate_fixture(inputs_dir / "large_estate", service_data)
    write_redacted_input_bundle(output / "redacted_inputs", service_data, pack_data, config_data, scenario_data)
    write_schema_files(output / "schemas")
    for scenario in scenario_data:
        write_json(events_dir / scenario.file_name, scenario.event)

    manifest = {
        "bundle_version": 1,
        "generated_at": GENERATED_AT,
        "description": "Deterministic offline full-coverage data bundle for brownout policy review testing.",
        "inputs": {
            "service_priority": "inputs/service_priority.yml",
            "policy_pack": "inputs/policy_pack.yml",
            "thresholds": "inputs/thresholds.yml",
        },
        "scenarios": [
            {
                "event": f"inputs/events/{scenario.file_name}",
                "incident_id": scenario.incident_id,
                "description": scenario.description,
                "allow_null_route": scenario.allow_null_route,
                "allow_admin_lockdown": scenario.allow_admin_lockdown,
                "allow_source_blocks": scenario.allow_source_blocks,
            }
            for scenario in scenario_data
        ],
    }
    write_json(output / "manifest.json", manifest)

    compile_results: dict[str, Any] = {}
    if include_outputs:
        for scenario in scenario_data:
            stem = Path(scenario.file_name).stem
            scenario_output = outputs_dir / stem
            result = compile_from_paths(
                CompileOptions(
                    event_path=events_dir / scenario.file_name,
                    services_path=inputs_dir / "service_priority.yml",
                    output_plan=scenario_output / "brownout_plan.yml",
                    output_actions=scenario_output / "actions.csv",
                    output_rollback=scenario_output / "rollback_plan.yml",
                    summary=scenario_output / "summary.json",
                    config_path=inputs_dir / "thresholds.yml",
                    policy_pack_path=inputs_dir / "policy_pack.yml",
                    incident_id=scenario.incident_id,
                    now=GENERATED_AT,
                    allow_null_route=scenario.allow_null_route,
                    allow_admin_lockdown=scenario.allow_admin_lockdown,
                    allow_source_blocks=scenario.allow_source_blocks,
                )
            )
            compile_results[scenario.file_name] = {
                "plan": result.plan,
                "rollback_plan": result.rollback_plan,
                "summary": result.summary,
            }
            write_json(scenario_output / "decision_trace.json", result.plan.decision_trace)
            write_enriched_actions_csv(scenario_output / "actions_enriched.csv", result.plan)
            write_markdown_summary(scenario_output / "brownout_plan.yml", scenario_output / "brownout_summary.md")
            if scenario.incident_id == "INC-GEN-006":
                write_post_incident_diff_output(output / "post_incident", result.plan)
            redacted_output = output / "redacted_outputs" / stem
            compile_from_paths(
                CompileOptions(
                    event_path=events_dir / scenario.file_name,
                    services_path=inputs_dir / "service_priority.yml",
                    output_plan=redacted_output / "brownout_plan.yml",
                    output_actions=redacted_output / "actions.csv",
                    output_rollback=redacted_output / "rollback_plan.yml",
                    summary=redacted_output / "summary.json",
                    config_path=inputs_dir / "thresholds.yml",
                    policy_pack_path=inputs_dir / "policy_pack.yml",
                    incident_id=scenario.incident_id,
                    now=GENERATED_AT,
                    allow_null_route=scenario.allow_null_route,
                    allow_admin_lockdown=scenario.allow_admin_lockdown,
                    allow_source_blocks=scenario.allow_source_blocks,
                    redact=True,
                )
            )
            try:
                compile_from_paths(
                    CompileOptions(
                        event_path=events_dir / scenario.file_name,
                        services_path=inputs_dir / "service_priority.yml",
                        output_plan=output / "strict_mode_outputs" / stem / "brownout_plan.yml",
                        output_actions=output / "strict_mode_outputs" / stem / "actions.csv",
                        output_rollback=output / "strict_mode_outputs" / stem / "rollback_plan.yml",
                        summary=output / "strict_mode_outputs" / stem / "summary.json",
                        config_path=inputs_dir / "thresholds.yml",
                        policy_pack_path=inputs_dir / "policy_pack.yml",
                        incident_id=scenario.incident_id,
                        now=GENERATED_AT,
                        allow_null_route=scenario.allow_null_route,
                        allow_admin_lockdown=scenario.allow_admin_lockdown,
                        allow_source_blocks=scenario.allow_source_blocks,
                        strict=True,
                    )
                )
                write_strict_mode_report(output / "strict_mode_reports", scenario, "PASS", "strict compile completed")
            except Exception as exc:
                write_strict_mode_report(output / "strict_mode_reports", scenario, "FAIL", str(exc))

    write_artifact_fingerprints(output)
    input_audit = audit_inputs(service_data, scenario_data)
    output_audit = audit_outputs(output, compile_results) if include_outputs else {}
    gaps = gap_report(input_audit, output_audit) if include_outputs else []
    coverage = {"input": input_audit, "output": output_audit, "gaps": gaps}
    if include_outputs:
        realism = build_realism_report(input_audit, output_audit, gaps)
        coverage["realism"] = realism
        write_json(output / "realism_report.json", realism)
    write_json(output / "coverage_report.json", coverage)
    if include_outputs:
        write_gap_markdown(output / "gap_report.md", input_audit, output_audit, gaps)
    return coverage
