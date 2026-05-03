from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from .action_model import CSV_COLUMNS
from .decision_package import build_decision_brief, decision_brief_markdown
from .models import ActionCsvRow, BrownoutAction, BrownoutPlan, RiskLevel, RollbackPlan, Summary, SummaryActions, SummaryInput
from .redact import redact_value, service_display_name_map


INFORMATIONAL_WARNINGS = {
    "POLICY_PACK_NOT_SUPPLIED_USING_DEFAULT",
    "REVIEW_ONLY_OUTPUT",
    "SERVICE_HAS_NO_TRUSTED_SOURCES",
    "SOURCE_PREFIXES_ADVISORY_ONLY",
}


def serializable(model: Any) -> Any:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json", exclude_none=True)
    return model


def write_yaml(path: str | Path, data: Any, redact: bool = False, service_names: list[str] | None = None) -> None:
    payload = serializable(data)
    if redact:
        payload = redact_value(payload, service_display_name_map(service_names or []))
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(payload, sort_keys=False))


def write_json(path: str | Path, data: Any, redact: bool = False, service_names: list[str] | None = None) -> None:
    payload = serializable(data)
    if redact:
        payload = redact_value(payload, service_display_name_map(service_names or []))
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def format_list(value: list[Any]) -> str:
    return "; ".join(str(item) for item in value)


def action_to_csv_row(action: BrownoutAction) -> ActionCsvRow:
    return ActionCsvRow(
        action_id=action.action_id,
        action_type=action.action_type.value,
        service_id=action.service_id,
        service_display_name=action.service_display_name or action.service_id,
        service_priority=action.service_priority.value,
        brownout_mode=action.brownout_mode.value,
        target_ip=action.target.ip,
        protocol=action.target.protocol,
        ports=format_list(action.target.ports or []),
        ttl_minutes=action.ttl_minutes,
        expires_at=action.expires_at.isoformat().replace("+00:00", "Z"),
        approval_required=action.approval_required,
        risk_level=action.risk_level.value,
        reason_codes=format_list(action.reason_codes),
        business_impact=format_list(action.business_impact),
        safety_notes=format_list(action.safety_notes),
        rollback_action_id=action.rollback_action_id,
        suggested_operator_question=format_list(action.suggested_operator_question),
    )


def write_actions_csv(path: str | Path, actions: list[BrownoutAction], redact: bool = False) -> None:
    service_names = sorted({name for action in actions for name in (action.service_id, action.service_display_name or action.service_id) if name})
    display_name_map = service_display_name_map(service_names)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for action in actions:
            row = action_to_csv_row(action).model_dump(mode="json")
            if redact:
                row = redact_value(row, display_name_map)
            writer.writerow(row)


def build_summary(
    incident_id: str,
    event_id: str,
    event_target_count: int,
    service_group_count: int,
    matched_service_count: int,
    unmatched_event_target_count: int,
    actions: list[BrownoutAction],
    warnings: list[str],
    blockers: list[str],
) -> Summary:
    by_type = Counter(action.action_type.value for action in actions)
    by_priority = Counter(action.service_priority.value for action in actions)
    risk_order = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
    risk = {level.value: 0 for level in risk_order}
    risk.update(Counter(action.risk_level.value for action in actions))
    questions: list[str] = []
    for action in actions:
        for question in action.suggested_operator_question:
            if question not in questions:
                questions.append(question)
    review_driving_warnings = [warning for warning in warnings if warning not in INFORMATIONAL_WARNINGS]
    review_reasons: list[str] = []
    if blockers:
        review_reasons.append("blockers present")
    if any(action.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL} for action in actions):
        review_reasons.append("high or critical risk action present")
    if any(action.approval_required for action in actions):
        review_reasons.append("operator approval required")
    for warning in review_driving_warnings:
        review_reasons.append(f"warning: {warning}")
    if blockers:
        lint_status = "FAIL"
    elif any(action.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL} for action in actions):
        lint_status = "REVIEW"
    elif review_driving_warnings or any(action.approval_required for action in actions):
        lint_status = "REVIEW"
    else:
        lint_status = "PASS"
    return Summary(
        incident_id=incident_id,
        event_id=event_id,
        lint_status=lint_status,
        input=SummaryInput(
            event_targets=event_target_count,
            service_groups=service_group_count,
            matched_services=matched_service_count,
            unmatched_event_targets=unmatched_event_target_count,
        ),
        actions=SummaryActions(
            total=len(actions),
            by_type=dict(sorted(by_type.items())),
            by_priority=dict(sorted(by_priority.items())),
            approval_required=sum(1 for action in actions if action.approval_required),
        ),
        risk={level.value: risk.get(level.value, 0) for level in risk_order},
        warnings=warnings,
        blockers=blockers,
        confidence_distribution=dict(sorted(Counter(action.confidence.value for action in actions).items())),
        ttl_distribution=dict(sorted(Counter(str(action.ttl_minutes) for action in actions).items(), key=lambda item: int(item[0]))),
        rollback_deadlines={action.action_id: action.expires_at.isoformat().replace("+00:00", "Z") for action in actions if action.action_type.value not in {"MONITOR_ONLY", "NO_ACTION"}},
        services_by_business_process=dict(sorted(Counter(action.business_process or "unspecified" for action in actions).items())),
        actions_by_owner=dict(sorted(Counter(action.owner or "unspecified" for action in actions).items())),
        actions_by_enforcement_point=dict(
            sorted(
                Counter(
                    str(point)
                    for action in actions
                    for point in (action.collateral_scope or {}).get("enforcement_points", [])
                ).items()
            )
        ),
        business_impact_totals={
            "action_groups": len({action.action_group_id for action in actions if action.action_group_id}),
            "approval_required_actions": sum(1 for action in actions if action.approval_required),
            "high_or_critical_actions": sum(1 for action in actions if action.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}),
            "distinct_business_processes": len({action.business_process for action in actions if action.business_process}),
        },
        review_reasons=review_reasons,
        recommended_operator_questions=questions,
    )


def write_markdown_summary(plan_path: str | Path, output_markdown: str | Path) -> None:
    plan = yaml.safe_load(Path(plan_path).read_text()) or {}
    plan_model = BrownoutPlan.model_validate(plan)
    brief = build_decision_brief(plan_model)
    output = Path(output_markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(decision_brief_markdown(brief))
