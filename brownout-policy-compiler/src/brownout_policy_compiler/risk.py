from __future__ import annotations

from .models import ActionType, RiskLevel, ServiceGroup


RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


def max_risk(*levels: RiskLevel) -> RiskLevel:
    return max(levels, key=lambda item: RISK_ORDER[item])


def default_risk_for_action(action_type: ActionType) -> RiskLevel:
    if action_type in {ActionType.PRIORITIZE, ActionType.MONITOR_ONLY, ActionType.NO_ACTION, ActionType.ALLOW_TRUSTED_SOURCES}:
        return RiskLevel.LOW
    if action_type in {ActionType.RATE_LIMIT, ActionType.RATE_LIMIT_UNTRUSTED, ActionType.DEPRIORITIZE, ActionType.CHALLENGE}:
        return RiskLevel.MEDIUM
    if action_type in {ActionType.DENY_UNTRUSTED, ActionType.TEMPORARY_BLOCK_PORT}:
        return RiskLevel.HIGH
    if action_type == ActionType.TEMPORARY_NULL_ROUTE:
        return RiskLevel.CRITICAL
    if action_type == ActionType.SHED_LOW_PRIORITY:
        return RiskLevel.MEDIUM
    return RiskLevel.MEDIUM


def score_risk(action_type: ActionType, service: ServiceGroup, pack_default: RiskLevel | None = None) -> RiskLevel:
    risk = pack_default or default_risk_for_action(action_type)
    if action_type == ActionType.SHED_LOW_PRIORITY and service.priority.value == "P3":
        risk = max_risk(risk, RiskLevel.HIGH)
    if action_type == ActionType.TEMPORARY_NULL_ROUTE:
        risk = RiskLevel.CRITICAL
    if service.approval_required:
        risk = max_risk(risk, RiskLevel.HIGH)
    if service.id in {"admin_access", "vpn_access"} and action_type != ActionType.PRIORITIZE:
        risk = max_risk(risk, RiskLevel.HIGH)
    return risk
