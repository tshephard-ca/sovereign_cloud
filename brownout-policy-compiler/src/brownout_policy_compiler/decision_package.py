from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .models import ActionType, BrownoutAction, BrownoutPlan, Priority, RiskLevel, RollbackPlan, Summary
from .redact import redact_value, service_display_name_map


PROTECT_ACTIONS = {
    ActionType.ALLOW_TRUSTED_SOURCES,
    ActionType.PRIORITIZE,
    ActionType.RATE_LIMIT_UNTRUSTED,
    ActionType.CHALLENGE,
}
DEGRADE_ACTIONS = {
    ActionType.RATE_LIMIT,
    ActionType.SHED_LOW_PRIORITY,
    ActionType.DEPRIORITIZE,
    ActionType.TEMPORARY_BLOCK_PORT,
    ActionType.TEMPORARY_NULL_ROUTE,
    ActionType.DENY_UNTRUSTED,
}
NO_CHANGE_ACTIONS = {ActionType.MONITOR_ONLY, ActionType.NO_ACTION}


def _dt(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat().replace("+00:00", "Z")
    return str(value)


def _target(action: BrownoutAction) -> dict[str, Any]:
    return {
        "ip": action.target.ip,
        "protocol": action.target.protocol,
        "ports": action.target.ports or [],
    }


def _question(action: BrownoutAction) -> str:
    return action.suggested_operator_question[0] if action.suggested_operator_question else ""


def _action_entry(action: BrownoutAction, queue: str) -> dict[str, Any]:
    return {
        "queue": queue,
        "action_id": action.action_id,
        "action_group_id": action.action_group_id,
        "action_group_role": action.action_group_role,
        "exclusive_or_staged": action.action_group_exclusive,
        "action_type": action.action_type.value,
        "service_id": action.service_id,
        "service_display_name": action.service_display_name or action.service_id,
        "service_priority": action.service_priority.value,
        "business_process": action.business_process,
        "owner": action.owner,
        "approver": action.approver,
        "rollback_owner": action.rollback_owner,
        "risk_level": action.risk_level.value,
        "confidence": action.confidence.value,
        "ttl_minutes": action.ttl_minutes,
        "decision_required_by": _dt(action.decision_required_by),
        "rollback_by": _dt(action.expires_at),
        "rollback_action_id": action.rollback_action_id,
        "approval_required": action.approval_required,
        "target": _target(action),
        "operator_question": _question(action),
        "why": action.reason_text[0] if action.reason_text else "",
        "business_impact": action.business_impact[0] if action.business_impact else "",
        "safety_note": action.safety_notes[0] if action.safety_notes else "",
    }


def _queue_for(action: BrownoutAction) -> str:
    if action.action_type in NO_CHANGE_ACTIONS:
        return "review_only"
    if action.action_type in DEGRADE_ACTIONS:
        return "degrade_candidate"
    if action.service_priority in {Priority.P0, Priority.P1} and action.action_type in PROTECT_ACTIONS:
        return "protect_now"
    return "review_only"


def _blocked_actions(plan: BrownoutPlan) -> list[dict[str, Any]]:
    details = list(plan.blocker_details)
    detailed_codes = {str(item.get("blocker")) for item in details}
    for code in plan.blockers:
        if code not in detailed_codes:
            details.append({"blocker": code, "reason": "Compiler safety or validation blocker."})
    return details


def _rollback_clock(actions: list[BrownoutAction], rollback_plan: RollbackPlan | None) -> dict[str, Any]:
    rollback_actions = rollback_plan.rollback_actions if rollback_plan else []
    by_service = Counter(item.service_id for item in rollback_actions)
    return {
        "rollback_deadline": _dt(rollback_plan.rollback_deadline) if rollback_plan else min((_dt(action.expires_at) for action in actions if action.action_type not in NO_CHANGE_ACTIONS), default=None),
        "rollback_action_count": len(rollback_actions) if rollback_plan else sum(1 for action in actions if action.action_type not in NO_CHANGE_ACTIONS),
        "rollback_actions_by_service": dict(sorted(by_service.items())),
        "rollback_required_action_ids": [action.action_id for action in actions if action.action_type not in NO_CHANGE_ACTIONS],
    }


def build_decision_brief(
    plan: BrownoutPlan,
    rollback_plan: RollbackPlan | None = None,
    summary: Summary | None = None,
) -> dict[str, Any]:
    queues = {"protect_now": [], "degrade_candidates": [], "review_only": []}
    approval_queue: list[dict[str, Any]] = []
    for action in plan.actions:
        queue = _queue_for(action)
        entry = _action_entry(action, queue)
        if queue == "protect_now":
            queues["protect_now"].append(entry)
        elif queue == "degrade_candidate":
            queues["degrade_candidates"].append(entry)
        else:
            queues["review_only"].append(entry)
        if action.approval_required or action.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            approval_queue.append(entry)

    questions: list[str] = []
    for action in plan.actions:
        for question in action.suggested_operator_question:
            if question not in questions:
                questions.append(question)

    status = summary.lint_status if summary else ("FAIL" if plan.blockers else "REVIEW" if approval_queue else "PASS")
    high_or_critical = [action for action in plan.actions if action.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}]
    degraded_services = sorted({item["service_id"] for item in queues["degrade_candidates"]})
    protected_services = sorted({item["service_id"] for item in queues["protect_now"]})
    return {
        "decision_brief_version": 1,
        "incident_id": plan.incident_id,
        "event_id": plan.event_id,
        "status": status,
        "mode": plan.mode,
        "generated_at": _dt(plan.generated_at),
        "expires_at": _dt(plan.expires_at),
        "first_read": {
            "protect_now_count": len(queues["protect_now"]),
            "degrade_candidate_count": len(queues["degrade_candidates"]),
            "approval_queue_count": len(approval_queue),
            "blocked_action_count": len(_blocked_actions(plan)),
            "review_only_count": len(queues["review_only"]),
            "rollback_deadline": _rollback_clock(plan.actions, rollback_plan)["rollback_deadline"],
        },
        "business_throughline": {
            "protected_services": protected_services,
            "degraded_services": degraded_services,
            "high_or_critical_action_count": len(high_or_critical),
            "message": "Preserve critical recovery/control paths, shift pressure to preapproved lower-priority services, block unsafe actions, and verify rollback.",
        },
        "protect_now": queues["protect_now"],
        "degrade_candidates": queues["degrade_candidates"],
        "approval_queue": approval_queue,
        "blocked_actions": _blocked_actions(plan),
        "review_only": queues["review_only"],
        "operator_questions": questions,
        "rollback_clock": _rollback_clock(plan.actions, rollback_plan),
        "evidence_quality": {
            "warnings": plan.warnings,
            "blockers": plan.blockers,
            "action_count": plan.action_count,
            "confidence_distribution": summary.confidence_distribution if summary else dict(Counter(action.confidence.value for action in plan.actions)),
            "risk_distribution": summary.risk if summary else dict(Counter(action.risk_level.value for action in plan.actions)),
        },
        "action_groups": plan.action_groups,
        "assumptions": plan.assumptions,
    }


def _serializable(data: Any) -> Any:
    if hasattr(data, "model_dump"):
        return data.model_dump(mode="json", exclude_none=True)
    return data


def _redact(data: Any, redact: bool, service_names: list[str] | None) -> Any:
    if not redact:
        return data
    return redact_value(data, service_display_name_map(service_names or []))


def write_decision_brief_json(path: str | Path, brief: dict[str, Any], *, redact: bool = False, service_names: list[str] | None = None) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = _redact(_serializable(brief), redact, service_names)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_rollback_clock_json(path: str | Path, brief: dict[str, Any], *, redact: bool = False, service_names: list[str] | None = None) -> None:
    write_decision_brief_json(path, brief["rollback_clock"], redact=redact, service_names=service_names)


def write_blocked_actions_json(path: str | Path, brief: dict[str, Any], *, redact: bool = False, service_names: list[str] | None = None) -> None:
    write_decision_brief_json(path, {"blocked_actions": brief["blocked_actions"]}, redact=redact, service_names=service_names)


def _csv_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    if value is None:
        return ""
    return str(value)


QUEUE_COLUMNS = [
    "queue",
    "action_id",
    "action_group_id",
    "action_type",
    "service_id",
    "service_display_name",
    "service_priority",
    "risk_level",
    "confidence",
    "ttl_minutes",
    "decision_required_by",
    "rollback_by",
    "approval_required",
    "owner",
    "approver",
    "rollback_owner",
    "operator_question",
    "business_impact",
]


def _write_queue_csv(path: str | Path, rows: list[dict[str, Any]], *, redact: bool = False, service_names: list[str] | None = None) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    display_name_map = service_display_name_map(service_names or [])
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUEUE_COLUMNS)
        writer.writeheader()
        for row in rows:
            payload = {
                "queue": row.get("queue", ""),
                "action_id": row.get("action_id", ""),
                "action_group_id": row.get("action_group_id", ""),
                "action_type": row.get("action_type", ""),
                "service_id": row.get("service_id", ""),
                "service_display_name": row.get("service_display_name", ""),
                "service_priority": row.get("service_priority", ""),
                "risk_level": row.get("risk_level", ""),
                "confidence": row.get("confidence", ""),
                "ttl_minutes": row.get("ttl_minutes", ""),
                "decision_required_by": row.get("decision_required_by", ""),
                "rollback_by": row.get("rollback_by", ""),
                "approval_required": row.get("approval_required", False),
                "owner": row.get("owner", ""),
                "approver": row.get("approver", ""),
                "rollback_owner": row.get("rollback_owner", ""),
                "operator_question": row.get("operator_question", ""),
                "business_impact": row.get("business_impact", ""),
            }
            if redact:
                payload = redact_value(payload, display_name_map)
            writer.writerow({key: _csv_value(value) for key, value in payload.items()})


def write_operator_queue_csv(path: str | Path, brief: dict[str, Any], *, redact: bool = False, service_names: list[str] | None = None) -> None:
    rows = [*brief["protect_now"], *brief["degrade_candidates"], *brief["review_only"]]
    _write_queue_csv(path, rows, redact=redact, service_names=service_names)


def write_approval_queue_csv(path: str | Path, brief: dict[str, Any], *, redact: bool = False, service_names: list[str] | None = None) -> None:
    _write_queue_csv(path, brief["approval_queue"], redact=redact, service_names=service_names)


def decision_brief_markdown(brief: dict[str, Any], *, include_action_inventory: bool = True) -> str:
    first = brief["first_read"]
    lines = [
        "# Brownout Decision Brief",
        "",
        f"- Incident ID: `{brief['incident_id']}`",
        f"- Event ID: `{brief['event_id']}`",
        f"- Status: `{brief['status']}`",
        f"- Mode: `{brief['mode']}`",
        f"- Protect-now actions: `{first['protect_now_count']}`",
        f"- Degradation candidates: `{first['degrade_candidate_count']}`",
        f"- Approval queue: `{first['approval_queue_count']}`",
        f"- Blocked actions: `{first['blocked_action_count']}`",
        f"- Rollback deadline: `{first['rollback_deadline'] or 'not required'}`",
        "",
        "## Business Throughline",
        "",
        brief["business_throughline"]["message"],
        "",
        "## Protect Now",
        "",
    ]
    lines.extend(_markdown_entries(brief["protect_now"], empty="No protect-now actions were generated."))
    lines.extend(["", "## Degrade Candidates", ""])
    lines.extend(_markdown_entries(brief["degrade_candidates"], empty="No degradation candidates were generated."))
    lines.extend(["", "## Approval Queue", ""])
    lines.extend(_markdown_entries(brief["approval_queue"], empty="No high-risk or approval-required actions were generated."))
    lines.extend(["", "## Blocked Actions", ""])
    if brief["blocked_actions"]:
        for item in brief["blocked_actions"]:
            lines.append(f"- `{item.get('blocker')}`: {item.get('reason', 'review required')}")
    else:
        lines.append("- No compiler blockers.")
    lines.extend(["", "## Operator Questions", ""])
    if brief["operator_questions"]:
        lines.extend(f"- {question}" for question in brief["operator_questions"])
    else:
        lines.append("- No operator questions.")
    lines.extend(["", "## Warnings", ""])
    if brief["evidence_quality"]["warnings"]:
        lines.extend(f"- {warning}" for warning in brief["evidence_quality"]["warnings"])
    else:
        lines.append("- No warnings.")
    if include_action_inventory:
        lines.extend(["", "## Actions", ""])
        rows = [*brief["protect_now"], *brief["degrade_candidates"], *brief["review_only"]]
        lines.extend(_markdown_entries(rows, empty="No actions generated."))
    return "\n".join(lines).rstrip() + "\n"


def _markdown_entries(entries: list[dict[str, Any]], *, empty: str) -> list[str]:
    if not entries:
        return [f"- {empty}"]
    lines: list[str] = []
    for entry in entries:
        lines.extend(
            [
                f"### {entry['action_id']} {entry['action_type']}",
                "",
                f"- Service: `{entry['service_id']}`",
                f"- Priority: `{entry['service_priority']}`",
                f"- Risk: `{entry['risk_level']}`",
                f"- TTL minutes: `{entry['ttl_minutes']}`",
                f"- Rollback by: `{entry['rollback_by']}`",
                f"- Business impact: {entry['business_impact']}",
            ]
        )
        if entry.get("operator_question"):
            lines.append(f"- Operator question: {entry['operator_question']}")
        lines.append("")
    return lines


def write_decision_brief_markdown(path: str | Path, brief: dict[str, Any], *, redact: bool = False, service_names: list[str] | None = None) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = _redact(_serializable(brief), redact, service_names)
    output.write_text(decision_brief_markdown(payload))
