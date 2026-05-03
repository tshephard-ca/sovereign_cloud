from __future__ import annotations

from datetime import datetime

from .models import BrownoutAction, RollbackAction, RollbackPlan


ROLLBACK_EXEMPT_ACTION_TYPES = {"MONITOR_ONLY", "NO_ACTION"}


def verification_steps_for(action: BrownoutAction) -> list[str]:
    label = action.service_display_name or action.service_id
    by_action = action.rollback_control.get("verification_steps_by_action") if action.rollback_control else None
    if isinstance(by_action, dict) and action.action_type.value in by_action:
        return [str(step) for step in by_action[action.action_type.value]]
    configured_steps = action.rollback_control.get("verification_steps") if action.rollback_control else None
    if configured_steps:
        return [str(step) for step in configured_steps]
    if action.action_type.value == "PRIORITIZE":
        return [
            f"Confirm temporary priority handling for {label} is removed or returned to baseline.",
            "Confirm baseline service policy is active.",
            "Confirm monitoring shows no unexpected degradation after rollback.",
        ]
    if action.action_type.value == "SHED_LOW_PRIORITY":
        return [
            f"Confirm temporary shedding for {label} is removed.",
            "Confirm baseline service availability policy is active.",
            "Confirm monitoring shows expected recovery for legitimate traffic.",
        ]
    if action.action_type.value == "TEMPORARY_NULL_ROUTE":
        return [
            f"Confirm temporary null-route candidate for {label} is no longer active.",
            "Confirm destination reachability is restored through approved paths.",
            "Confirm no shared service remains unintentionally unavailable.",
        ]
    return [
        f"Confirm temporary policy for {label} is removed.",
        "Confirm baseline service policy is active.",
        "Confirm monitoring shows no unexpected deny or rate-limit spike.",
    ]


def make_rollback_plan(
    incident_id: str,
    event_id: str,
    generated_at: datetime,
    actions: list[BrownoutAction],
) -> RollbackPlan:
    rollback_actions: list[RollbackAction] = []
    for action in reversed(actions):
        if action.action_type.value in ROLLBACK_EXEMPT_ACTION_TYPES:
            continue
        rollback_actions.append(
            RollbackAction(
                rollback_action_id=action.rollback_action_id,
                action_id=action.action_id,
                service_id=action.service_id,
                rollback_owner=action.rollback_owner,
                escalation_contact=action.rollback_control.get("escalation_contact") if action.rollback_control else None,
                rollback_by=action.expires_at,
                expected_policy_state_after_rollback=action.rollback_control.get("expected_baseline_state", "pre-incident service policy restored") if action.rollback_control else "pre-incident service policy restored",
                verification_steps=verification_steps_for(action),
                evidence_required=action.rollback_control.get("evidence_required", []) if action.rollback_control else [],
                reason_codes=["TTL_ROLLBACK_REQUIRED", f"{action.service_priority.value}_SERVICE_POLICY_RESTORE_REQUIRED"],
            )
        )
    rollback_required_actions = [action for action in actions if action.action_type.value not in ROLLBACK_EXEMPT_ACTION_TYPES]
    deadline = min((action.expires_at for action in rollback_required_actions), default=generated_at)
    return RollbackPlan(
        incident_id=incident_id,
        event_id=event_id,
        generated_at=generated_at,
        rollback_deadline=deadline,
        rollback_actions=rollback_actions,
    )
