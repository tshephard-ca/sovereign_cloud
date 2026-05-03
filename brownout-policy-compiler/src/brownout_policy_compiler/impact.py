from __future__ import annotations

from .models import ActionType, ServiceGroup


def _service_context(service: ServiceGroup) -> str:
    process = service.business_process or "business process not supplied"
    owner = service.owner or "owner not supplied"
    users = service.user_population or "affected users not quantified"
    impact = service.revenue_impact or "impact not quantified"
    slo = service.slo or "SLO not supplied"
    dependencies = ", ".join(item.service_id for item in service.depends_on) if service.depends_on else "none declared"
    return f"Business process: {process}; owner: {owner}; users: {users}; impact: {impact}; SLO: {slo}; dependencies: {dependencies}."


def business_impact_for(action_type: ActionType, service: ServiceGroup, ttl_minutes: int) -> list[str]:
    name = service.display_name or service.id
    extra = service.model_extra or {}
    action_impacts = extra.get("degradation_impact_by_action", {})
    action_specific = action_impacts.get(action_type.value) if isinstance(action_impacts, dict) else None
    impact_summary = action_specific or extra.get("impact_summary")

    if action_type == ActionType.ALLOW_TRUSTED_SOURCES:
        headline = f"Trusted-source access to {name} is preserved for up to {ttl_minutes} minutes."
    elif action_type == ActionType.PRIORITIZE:
        headline = f"{name} receives priority ahead of lower-priority traffic for up to {ttl_minutes} minutes."
    elif action_type == ActionType.RATE_LIMIT_UNTRUSTED:
        headline = f"Traffic outside trusted sources for {name} is rate limited so priority users remain reachable."
    elif action_type == ActionType.DENY_UNTRUSTED:
        headline = f"Untrusted access to {name} is denied; users outside trusted ranges may be unable to reach it for up to {ttl_minutes} minutes."
    elif action_type == ActionType.SHED_LOW_PRIORITY:
        headline = f"{name} is intentionally degraded for up to {ttl_minutes} minutes to preserve higher-priority services."
    elif action_type == ActionType.CHALLENGE:
        headline = f"{name} receives application-edge checks; clients are challenged and automated clients may fail without review."
    elif action_type == ActionType.TEMPORARY_NULL_ROUTE:
        headline = f"Makes {name} intentionally unreachable for up to {ttl_minutes} minutes if explicitly approved."
    elif action_type == ActionType.TEMPORARY_BLOCK_PORT:
        headline = f"Selected {name} destination ports are intentionally unavailable for up to {ttl_minutes} minutes if explicitly approved."
    elif action_type == ActionType.NO_ACTION:
        headline = f"Recommends no temporary policy change for {name}; continue monitoring and review."
    elif action_type == ActionType.MONITOR_ONLY:
        headline = f"Recommends no temporary policy change for {name}; monitor evidence and map ownership before action."
    elif action_type == ActionType.RATE_LIMIT:
        headline = f"Traffic to {name} is rate limited for up to {ttl_minutes} minutes; legitimate users may see slower responses."
    elif action_type == ActionType.DEPRIORITIZE:
        headline = f"{name} is deprioritized behind higher-priority services for up to {ttl_minutes} minutes."
    else:
        headline = f"No temporary policy change is made for {name} by this review package."

    if impact_summary:
        headline = f"{headline} {impact_summary}"
    return [headline, _service_context(service)]
