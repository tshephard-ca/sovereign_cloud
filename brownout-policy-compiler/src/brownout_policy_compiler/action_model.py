from __future__ import annotations

from .models import ActionType


CSV_COLUMNS = [
    "action_id",
    "action_type",
    "service_id",
    "service_display_name",
    "service_priority",
    "brownout_mode",
    "target_ip",
    "protocol",
    "ports",
    "ttl_minutes",
    "expires_at",
    "approval_required",
    "risk_level",
    "reason_codes",
    "business_impact",
    "safety_notes",
    "rollback_action_id",
    "suggested_operator_question",
]


OPERATOR_QUESTIONS = {
    ActionType.ALLOW_TRUSTED_SOURCES: "Are the trusted source ranges current and complete?",
    ActionType.RATE_LIMIT_UNTRUSTED: "What legitimate users may be affected by untrusted-source rate limiting?",
    ActionType.RATE_LIMIT: "What legitimate users may be affected by temporary rate limiting?",
    ActionType.PRIORITIZE: "Which enforcement point can honor this priority without starving other critical services?",
    ActionType.DENY_UNTRUSTED: "Has the service owner approved restricting access to trusted sources only?",
    ActionType.SHED_LOW_PRIORITY: "Is this service safe to degrade for the proposed TTL?",
    ActionType.CHALLENGE: "Will browser/API challenges break automated legitimate clients?",
    ActionType.TEMPORARY_BLOCK_PORT: "What legitimate clients use this port, and is there a tested rollback?",
    ActionType.TEMPORARY_NULL_ROUTE: "What other services share this destination, and who approves intentional unavailability?",
    ActionType.MONITOR_ONLY: "What additional evidence is needed before action?",
    ActionType.NO_ACTION: "What additional evidence is needed before action?",
    ActionType.DEPRIORITIZE: "Which lower-priority traffic can be deprioritized without affecting critical workflows?",
}

