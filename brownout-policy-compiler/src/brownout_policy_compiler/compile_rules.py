from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .action_model import OPERATOR_QUESTIONS
from .classify_event import classify_attack_context
from .config import load_config
from .decision_package import (
    build_decision_brief,
    write_approval_queue_csv,
    write_blocked_actions_json,
    write_decision_brief_json,
    write_decision_brief_markdown,
    write_operator_queue_csv,
    write_rollback_clock_json,
)
from .event_schema import load_event, validate_event
from .impact import business_impact_for
from .models import (
    ActionTarget,
    ActionType,
    BrownoutAction,
    BrownoutMode,
    BrownoutPlan,
    CompilerConfig,
    Confidence,
    DdosEvent,
    MatchResult,
    PolicyPack,
    Priority,
    RateLimitProfile,
    RiskLevel,
    ServiceGroup,
    ServicePriorityFile,
    ValidationResult,
)
from .normalize import PRIORITY_ORDER, match_event_targets, services_sharing_destination
from .policy_pack import load_policy_pack
from .report import build_summary, write_actions_csv, write_json, write_yaml
from .risk import RISK_ORDER, score_risk
from .rollback import make_rollback_plan
from .service_priority import load_service_priority, validate_service_priority
from .validators import normalize_ports


RISK_SORT = {RiskLevel.CRITICAL: 0, RiskLevel.HIGH: 1, RiskLevel.MEDIUM: 2, RiskLevel.LOW: 3}
CONFIDENCE_SORT = {Confidence.HIGH: 3, Confidence.MEDIUM: 2, Confidence.LOW: 1}


@dataclass(frozen=True)
class CompileOptions:
    event_path: str | Path
    services_path: str | Path
    output_plan: str | Path
    output_actions: str | Path
    output_rollback: str | Path
    summary: str | Path
    config_path: str | Path | None = None
    policy_pack_path: str | Path | None = None
    incident_id: str | None = None
    now: str | None = None
    strict: bool = False
    redact: bool = False
    allow_null_route: bool = False
    allow_source_blocks: bool = False
    allow_admin_lockdown: bool = False
    max_actions: int | None = None
    decision_brief: str | Path | None = None
    decision_brief_markdown: str | Path | None = None
    operator_queue: str | Path | None = None
    approval_queue: str | Path | None = None
    rollback_clock: str | Path | None = None
    blocked_actions: str | Path | None = None


@dataclass
class CompileResult:
    plan: BrownoutPlan
    rollback_plan: object
    summary: object
    decision_brief: dict[str, object]
    decision_artifacts: dict[str, Path]
    warnings: list[str]
    blockers: list[str]


def parse_now(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC).replace(microsecond=0)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def combine_validation(*items: ValidationResult) -> ValidationResult:
    result = ValidationResult()
    for item in items:
        result.extend(item)
    result.warnings = sorted(set(result.warnings))
    result.blockers = sorted(set(result.blockers))
    return result


def priority_ttl(priority: Priority, config: CompilerConfig, pack: PolicyPack) -> int:
    config_value = getattr(config, f"{priority.value.lower()}_max_ttl_minutes")
    pack_value = getattr(pack.ttl, f"{priority.value.lower()}_max_minutes")
    return min(config_value, pack_value)


def ttl_for_action(
    action_type: ActionType,
    service: ServiceGroup,
    config: CompilerConfig,
    pack: PolicyPack,
) -> int:
    ttl = min(config.default_ttl_minutes, pack.ttl.default_minutes, priority_ttl(service.priority, config, pack))
    if service.max_ttl_minutes is not None:
        ttl = min(ttl, service.max_ttl_minutes)
    ttl = min(ttl, config.max_ttl_minutes)
    if action_type == ActionType.TEMPORARY_NULL_ROUTE:
        ttl = min(ttl, config.null_route_max_ttl_minutes, pack.ttl.null_route_max_minutes)
    return ttl


def lower_confidence(current: Confidence, *candidates: Confidence) -> Confidence:
    values = (current, *candidates)
    return min(values, key=lambda item: CONFIDENCE_SORT[item])


def confidence_for_action(match: MatchResult, action_type: ActionType, event: DdosEvent, service: ServiceGroup) -> Confidence:
    confidence = match.confidence
    if event.confidence == Confidence.LOW:
        confidence = Confidence.LOW
    elif event.confidence == Confidence.MEDIUM:
        confidence = lower_confidence(confidence, Confidence.MEDIUM)
    target = match.event_target
    if target.observed_bps is None and target.observed_pps is None:
        confidence = lower_confidence(confidence, Confidence.LOW)
    if target.baseline_bps is None and target.baseline_pps is None:
        confidence = lower_confidence(confidence, Confidence.LOW)
    if action_type in {ActionType.ALLOW_TRUSTED_SOURCES, ActionType.RATE_LIMIT_UNTRUSTED, ActionType.DENY_UNTRUSTED}:
        if not service.trusted_source_groups:
            confidence = Confidence.LOW
    return confidence


def service_has_trusted_sources(service: ServiceGroup, services: ServicePriorityFile) -> bool:
    return bool(service.trusted_source_groups) and all(group in services.trusted_sources for group in service.trusted_source_groups)


def select_profile(
    action_type: ActionType,
    service: ServiceGroup,
    protocol: str,
    pack: PolicyPack,
) -> tuple[str | None, RateLimitProfile | None]:
    if action_type not in {ActionType.RATE_LIMIT, ActionType.RATE_LIMIT_UNTRUSTED, ActionType.SHED_LOW_PRIORITY}:
        return None, None
    service_profile_map = (service.model_extra or {}).get("action_profiles", {})
    hinted_profile = service_profile_map.get(action_type.value) or service_profile_map.get("default")
    if hinted_profile and hinted_profile in pack.rate_limit_profiles:
        profile = pack.rate_limit_profiles[hinted_profile]
        if not profile.applies_to or protocol in profile.applies_to or "any" in profile.applies_to:
            return hinted_profile, profile
    candidates: list[tuple[str, RateLimitProfile]] = []
    for name, profile in pack.rate_limit_profiles.items():
        if not profile.applies_to or protocol in profile.applies_to or "any" in profile.applies_to:
            candidates.append((name, profile))
    if not candidates:
        return None, None
    if service.priority in {Priority.P0, Priority.P1}:
        for name, profile in candidates:
            if "critical" in name or "protect" in name:
                return name, profile
    for name, profile in candidates:
        if "low_priority" in name or "public" in name:
            return name, profile
    return candidates[0]


def base_reason_codes(
    action_type: ActionType,
    service: ServiceGroup,
    match: MatchResult,
    event: DdosEvent,
    policy_pack_supplied: bool,
) -> list[str]:
    codes = list(match.reason_codes)
    if service.priority == Priority.P0:
        codes.append("P0_SERVICE_PROTECTED")
    elif service.priority == Priority.P1:
        codes.append("P1_SERVICE_PROTECTED")
    elif service.priority in {Priority.P3, Priority.P4}:
        codes.append("LOW_PRIORITY_SERVICE")
    if service.trusted_source_groups:
        codes.append("TRUSTED_SOURCES_AVAILABLE")
    else:
        codes.append("TRUSTED_SOURCES_MISSING")
    if action_type in {ActionType.RATE_LIMIT, ActionType.RATE_LIMIT_UNTRUSTED}:
        codes.append("RATE_LIMIT_ALLOWED_BY_SERVICE_POLICY")
    if action_type == ActionType.SHED_LOW_PRIORITY:
        codes.append("SHED_ALLOWED_BY_SERVICE_POLICY")
    if action_type == ActionType.PRIORITIZE:
        codes.append("PRIORITIZE_SELECTED_FOR_CRITICAL_SERVICE")
    if action_type == ActionType.CHALLENGE:
        codes.append("CHALLENGE_SELECTED_FOR_APPLICATION_ATTACK")
    if action_type == ActionType.DENY_UNTRUSTED:
        codes.append("DENY_UNTRUSTED_REQUIRES_APPROVAL")
    if action_type == ActionType.TEMPORARY_NULL_ROUTE:
        codes.append("NULL_ROUTE_ALLOWED_BY_FLAG")
    if event.provider_actions_already_active:
        codes.append("PROVIDER_MITIGATION_ALREADY_ACTIVE")
    codes.append("TEMPORARY_TTL_APPLIED")
    codes.append("ROLLBACK_REQUIRED")
    codes.append("REVIEW_ONLY_MODE")
    codes.append("NO_LIVE_ENFORCEMENT")
    codes.append("USER_POLICY_PACK_USED" if policy_pack_supplied else "POLICY_PACK_DEFAULT_USED")
    if event.attack_class.value == "UNKNOWN":
        codes.append("UNKNOWN_ATTACK_CLASS")
    if event.confidence == Confidence.LOW:
        codes.append("LOW_CONFIDENCE_EVENT")
    return sorted(set(codes), key=codes.index)


def reason_text_for(action_type: ActionType, service: ServiceGroup) -> list[str]:
    if service.priority in {Priority.P0, Priority.P1}:
        priority_text = f"Target appears in the mitigation event and is mapped to a {service.priority.value} service."
    else:
        priority_text = f"Target appears in the mitigation event and is mapped to a {service.priority.value} service."
    if action_type == ActionType.ALLOW_TRUSTED_SOURCES:
        return [priority_text, "Trusted source access is preserved without denying other traffic by itself."]
    if action_type == ActionType.PRIORITIZE:
        return [priority_text, "Temporary priority is suggested as an abstract review-only action."]
    if action_type == ActionType.RATE_LIMIT_UNTRUSTED:
        return [priority_text, "Traffic outside trusted sources should be rate-limited rather than broadly denied."]
    if action_type == ActionType.DENY_UNTRUSTED:
        return [priority_text, "Restricting access to trusted sources only requires explicit operator approval."]
    if action_type == ActionType.SHED_LOW_PRIORITY:
        return [priority_text, "The service policy allows temporary degradation of lower-priority traffic."]
    if action_type == ActionType.CHALLENGE:
        return [priority_text, "Application-layer indicators support reviewing an abstract challenge action."]
    if action_type == ActionType.TEMPORARY_NULL_ROUTE:
        return [priority_text, "Null-route review is enabled by flag and remains a high-impact temporary candidate."]
    if action_type == ActionType.TEMPORARY_BLOCK_PORT:
        return [priority_text, "Temporary destination-port blocking is a high-impact review-only action for lower-priority traffic."]
    if action_type == ActionType.NO_ACTION:
        return [priority_text, "The service-priority policy explicitly selects no temporary policy action for this service."]
    if action_type == ActionType.RATE_LIMIT:
        return [priority_text, "The service policy allows temporary rate limiting."]
    if action_type == ActionType.DEPRIORITIZE:
        return [priority_text, "Lower-priority traffic can be deprioritized to preserve higher-priority services."]
    return [priority_text]


def safety_notes_for(action_type: ActionType, service: ServiceGroup, event: DdosEvent) -> list[str]:
    notes = ["Compiler did not verify live device state."]
    if action_type in {ActionType.ALLOW_TRUSTED_SOURCES, ActionType.RATE_LIMIT_UNTRUSTED, ActionType.DENY_UNTRUSTED}:
        notes.append("Do not apply if trusted source list is stale.")
    if action_type == ActionType.DENY_UNTRUSTED:
        notes.append("Review service-owner approval before restricting untrusted access.")
    if action_type == ActionType.SHED_LOW_PRIORITY:
        notes.append("This action may reduce service availability for legitimate users.")
    if action_type == ActionType.CHALLENGE:
        notes.append("Challenges may affect legitimate automated clients.")
    if action_type == ActionType.TEMPORARY_NULL_ROUTE:
        notes.append("Severe risk: intentional destination unavailability may affect shared services.")
    if action_type == ActionType.TEMPORARY_BLOCK_PORT:
        notes.append("Blocking a destination port may interrupt legitimate clients that depend on that port.")
    if event.signals.spoofing_likely:
        notes.append("Source prefixes are advisory because spoofing_likely=true.")
    if service.id == "vpn_access":
        notes.append("Review with the service owner if VPN access is customer-facing.")
    return notes


def risk_factors_for(action_type: ActionType, service: ServiceGroup, match: MatchResult, risk: RiskLevel) -> list[str]:
    factors = [f"base_action_risk:{action_type.value}", f"service_priority:{service.priority.value}", f"computed_risk:{risk.value}"]
    if service.approval_required or action_type in {ActionType.DENY_UNTRUSTED, ActionType.TEMPORARY_NULL_ROUTE}:
        factors.append("operator_approval_required")
    if service.id in {"admin_access", "vpn_access"} and action_type != ActionType.PRIORITIZE:
        factors.append("admin_or_vpn_access_context")
    if action_type in {ActionType.TEMPORARY_BLOCK_PORT, ActionType.TEMPORARY_NULL_ROUTE}:
        factors.append("connectivity_disruption_possible")
    if len(match.all_service_ids) > 1:
        factors.append("shared_destination_collateral_review")
    if not service.trusted_source_groups:
        factors.append("trusted_source_context_absent_or_not_applicable")
    return factors


def confidence_rationale_for(match: MatchResult, event: DdosEvent, service: ServiceGroup, action_type: ActionType, confidence: Confidence) -> list[str]:
    rationale = [f"computed_confidence:{confidence.value}", f"event_confidence:{event.confidence.value}", f"match_confidence:{match.confidence.value}"]
    if match.event_target.ports is None:
        rationale.append("event_target_ports_missing_lowered_confidence")
    if match.event_target.observed_bps is None and match.event_target.observed_pps is None:
        rationale.append("event_target_metrics_missing_lowered_confidence")
    if match.event_target.baseline_bps is None and match.event_target.baseline_pps is None:
        rationale.append("event_baseline_missing_lowered_confidence")
    if action_type in {ActionType.ALLOW_TRUSTED_SOURCES, ActionType.RATE_LIMIT_UNTRUSTED, ActionType.DENY_UNTRUSTED}:
        rationale.append("trusted_sources_present" if service.trusted_source_groups else "trusted_sources_missing")
    if "CIDR_ENDPOINT_MATCH" in match.reason_codes:
        rationale.append("cidr_endpoint_match_lowered_confidence")
    return rationale


def collateral_scope_for(service: ServiceGroup, services: ServicePriorityFile, match: MatchResult, action_type: ActionType) -> dict[str, object]:
    sharing = services_sharing_destination(service, services, match.event_target.ip)
    endpoint_extra = match.endpoint.model_extra or {}
    scope = {
        "impacted_service_ids": sharing,
        "shared_endpoint_group": match.endpoint.shared_endpoint_group,
        "enforcement_points": [item.value for item in match.endpoint.enforcement_points],
        "collateral_review_required": len(sharing) > 1 or action_type in {ActionType.TEMPORARY_BLOCK_PORT, ActionType.TEMPORARY_NULL_ROUTE, ActionType.DENY_UNTRUSTED},
    }
    if endpoint_extra.get("region"):
        scope["region"] = endpoint_extra["region"]
    if endpoint_extra.get("endpoint_role"):
        scope["endpoint_role"] = endpoint_extra["endpoint_role"]
    return scope


def dump_optional_model(value: object | None) -> dict[str, object]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, dict):
        return value
    return {}


def parameters_for(action_type: ActionType, service: ServiceGroup, match: MatchResult, pack: PolicyPack, policy_pack_supplied: bool) -> dict[str, object]:
    parameters: dict[str, object] = {}
    profile_name, profile = select_profile(action_type, service, match.endpoint.protocol, pack)
    if profile_name:
        service_profile_map = (service.model_extra or {}).get("action_profiles", {})
        hinted_profile = service_profile_map.get(action_type.value) or service_profile_map.get("default")
        if action_type == ActionType.SHED_LOW_PRIORITY:
            parameters["shed_profile"] = profile_name
        else:
            parameters["rate_limit_profile"] = profile_name
        parameters["profile_selection_source"] = "SERVICE_ACTION_PROFILE" if hinted_profile == profile_name else "POLICY_PACK_PROTOCOL_MATCH"
        if profile.abstract_rate is not None:
            parameters["abstract_rate"] = profile.abstract_rate
        if profile.exact_rate is not None:
            parameters["exact_rate"] = profile.exact_rate
            parameters["evidence_source"] = "USER_POLICY_PACK" if policy_pack_supplied else "BUILT_IN_POLICY_PACK"
        parameters["profile_description"] = profile.description
        if action_type in {ActionType.RATE_LIMIT, ActionType.RATE_LIMIT_UNTRUSTED}:
            parameters["rate_limit_profile_selected"] = True
    if action_type == ActionType.TEMPORARY_NULL_ROUTE:
        parameters["null_route_review_only"] = True
    preferences = pack.action_preferences.get(service.priority, [])
    if action_type in preferences:
        parameters["policy_preference_source"] = "POLICY_PACK"
        parameters["policy_preference_rank"] = preferences.index(action_type) + 1
    return {key: value for key, value in parameters.items() if value is not None}


def apply_policy_preferences(candidates: list[ActionType], service: ServiceGroup, pack: PolicyPack) -> list[ActionType]:
    preferences = pack.action_preferences.get(service.priority, [])
    ordered = [action for action in preferences if action in candidates]
    ordered.extend(action for action in candidates if action not in ordered)
    return ordered


def selectors_for(action_type: ActionType, service: ServiceGroup) -> dict[str, object]:
    selectors: dict[str, object] = {}
    if action_type in {ActionType.ALLOW_TRUSTED_SOURCES, ActionType.RATE_LIMIT_UNTRUSTED, ActionType.DENY_UNTRUSTED}:
        selectors["trusted_source_groups"] = service.trusted_source_groups
    if action_type in {ActionType.RATE_LIMIT_UNTRUSTED, ActionType.DENY_UNTRUSTED}:
        selectors["untrusted_sources"] = True
    return selectors


def candidate_action_types(
    match: MatchResult,
    services: ServicePriorityFile,
    pack: PolicyPack,
    context: str,
    allow_null_route: bool,
    allow_admin_lockdown: bool,
    validation: ValidationResult,
) -> list[ActionType]:
    service = match.service
    allowed = set(service.allowed_actions)
    candidates: list[ActionType] = []
    trusted_available = service_has_trusted_sources(service, services)
    is_admin_lockdown = service.id == "admin_access" and service.brownout_mode == BrownoutMode.RESTRICT_TO_TRUSTED

    def add(action_type: ActionType) -> None:
        if action_type in allowed and action_type not in candidates:
            candidates.append(action_type)

    if service.brownout_mode == BrownoutMode.NO_ACTION:
        add(ActionType.NO_ACTION)
        if not candidates:
            add(ActionType.MONITOR_ONLY)
        return apply_policy_preferences(candidates, service, pack)

    if service.priority == Priority.P0:
        if allow_null_route and ActionType.TEMPORARY_NULL_ROUTE in allowed:
            validation.blockers.append("UNSAFE_NULL_ROUTE_REQUESTED")
        if trusted_available:
            add(ActionType.ALLOW_TRUSTED_SOURCES)
        add(ActionType.PRIORITIZE)
        if context == "application":
            add(ActionType.CHALLENGE)
        if trusted_available:
            add(ActionType.RATE_LIMIT_UNTRUSTED)
        return apply_policy_preferences(candidates, service, pack)

    if service.priority == Priority.P1:
        if allow_null_route and ActionType.TEMPORARY_NULL_ROUTE in allowed:
            validation.blockers.append("UNSAFE_NULL_ROUTE_REQUESTED")
        if trusted_available:
            add(ActionType.ALLOW_TRUSTED_SOURCES)
        add(ActionType.PRIORITIZE)
        if context == "application":
            add(ActionType.CHALLENGE)
        if trusted_available:
            add(ActionType.RATE_LIMIT_UNTRUSTED)
        add(ActionType.RATE_LIMIT)
        if service.brownout_mode == BrownoutMode.RESTRICT_TO_TRUSTED and ActionType.DENY_UNTRUSTED in allowed:
            if is_admin_lockdown and not allow_admin_lockdown:
                validation.warnings.append("APPROVAL_REQUIRED_ACTION_PRESENT")
            else:
                add(ActionType.DENY_UNTRUSTED)
        return apply_policy_preferences(candidates, service, pack)

    if service.priority == Priority.P2:
        if context == "application":
            add(ActionType.CHALLENGE)
        add(ActionType.RATE_LIMIT)
        add(ActionType.DEPRIORITIZE)
        return apply_policy_preferences(candidates, service, pack)

    if service.priority in {Priority.P3, Priority.P4}:
        if context == "application":
            add(ActionType.CHALLENGE)
        add(ActionType.SHED_LOW_PRIORITY)
        add(ActionType.RATE_LIMIT)
        add(ActionType.DEPRIORITIZE)
        add(ActionType.TEMPORARY_BLOCK_PORT)
        if ActionType.TEMPORARY_NULL_ROUTE in allowed:
            if allow_null_route and service.brownout_mode in {BrownoutMode.SHED, BrownoutMode.ISOLATE}:
                add(ActionType.TEMPORARY_NULL_ROUTE)
            elif allow_null_route:
                validation.blockers.append("UNSAFE_NULL_ROUTE_REQUESTED")
        return apply_policy_preferences(candidates, service, pack)

    return apply_policy_preferences(candidates, service, pack)


def enforce_null_route_safety(
    action_type: ActionType,
    match: MatchResult,
    services: ServicePriorityFile,
    ttl: int,
    config: CompilerConfig,
    validation: ValidationResult,
) -> bool:
    if action_type != ActionType.TEMPORARY_NULL_ROUTE:
        return True
    if match.service.priority in {Priority.P0, Priority.P1}:
        validation.blockers.append("UNSAFE_NULL_ROUTE_REQUESTED")
        return False
    if ttl > config.null_route_max_ttl_minutes:
        validation.blockers.append("UNSAFE_NULL_ROUTE_REQUESTED")
        return False
    sharing = services_sharing_destination(match.service, services, match.event_target.ip)
    if len(sharing) > 1:
        validation.blockers.append("NULL_ROUTE_COLLATERAL_RISK")
        validation.blocker_details.append(
            {
                "blocker": "NULL_ROUTE_COLLATERAL_RISK",
                "target_ip": match.event_target.ip,
                "candidate_service_id": match.service.id,
                "impacted_service_ids": sharing,
                "reason": "Temporary null-route would affect multiple service groups sharing the destination.",
            }
        )
        return False
    return True


def make_action(
    action_type: ActionType,
    match: MatchResult,
    event: DdosEvent,
    services: ServicePriorityFile,
    config: CompilerConfig,
    pack: PolicyPack,
    policy_pack_supplied: bool,
    generated_at: datetime,
    validation: ValidationResult,
) -> BrownoutAction | None:
    service = match.service
    if action_type not in service.allowed_actions:
        validation.blockers.append("ACTION_NOT_ALLOWED_BY_SERVICE_POLICY")
        return None
    if action_type in {ActionType.RATE_LIMIT_UNTRUSTED, ActionType.DENY_UNTRUSTED} and not service_has_trusted_sources(service, services):
        validation.blockers.append("TRUSTED_SOURCE_REQUIRED_BUT_MISSING")
        return None
    ttl = ttl_for_action(action_type, service, config, pack)
    if ttl <= 0:
        validation.blockers.append("TTL_MISSING")
        return None
    if not enforce_null_route_safety(action_type, match, services, ttl, config, validation):
        return None

    pack_risk = pack.risk_defaults.get(action_type)
    risk = score_risk(action_type, service, pack_risk)
    approval_required = service.approval_required or action_type in {ActionType.DENY_UNTRUSTED, ActionType.TEMPORARY_NULL_ROUTE}
    if approval_required:
        risk = RiskLevel.HIGH if RISK_ORDER[risk] < RISK_ORDER[RiskLevel.HIGH] else risk
    confidence = confidence_for_action(match, action_type, event, service)
    decision_required_by = generated_at + timedelta(minutes=max(1, min(ttl, 10)))
    reason_codes = base_reason_codes(action_type, service, match, event, policy_pack_supplied)
    params = parameters_for(action_type, service, match, pack, policy_pack_supplied)
    if params.get("rate_limit_profile_selected"):
        reason_codes.append("RATE_LIMIT_PROFILE_SELECTED")
    if approval_required:
        reason_codes.append("APPROVAL_REQUIRED")
    if action_type == ActionType.SHED_LOW_PRIORITY and service.priority in {Priority.P0, Priority.P1}:
        reason_codes.append("SHED_BLOCKED_FOR_HIGH_PRIORITY")

    return BrownoutAction(
        action_id="pending",
        action_type=action_type,
        service_id=service.id,
        service_display_name=service.display_name,
        service_priority=service.priority,
        brownout_mode=service.brownout_mode,
        business_process=service.business_process,
        owner=service.owner,
        approver=service.approver,
        rollback_owner=service.rollback_owner,
        approval_metadata=dump_optional_model(service.approval_metadata),
        rollback_control=dump_optional_model(service.rollback_control),
        target=ActionTarget(
            ip=match.event_target.ip,
            protocol=match.endpoint.protocol,
            ports=normalize_ports(match.event_target.ports or match.endpoint.ports),
        ),
        selectors=selectors_for(action_type, service),
        parameters=params,
        ttl_minutes=ttl,
        expires_at=generated_at + timedelta(minutes=ttl),
        decision_required_by=decision_required_by,
        rollback_action_id="pending",
        approval_required=approval_required,
        risk_level=risk,
        confidence=confidence,
        reason_codes=sorted(set(reason_codes), key=reason_codes.index),
        reason_text=reason_text_for(action_type, service),
        safety_notes=safety_notes_for(action_type, service, event),
        business_impact=business_impact_for(action_type, service, ttl),
        suggested_operator_question=[OPERATOR_QUESTIONS[action_type]]
        if risk in {RiskLevel.HIGH, RiskLevel.CRITICAL} or action_type in OPERATOR_QUESTIONS
        else [],
        risk_factors=risk_factors_for(action_type, service, match, risk),
        confidence_rationale=confidence_rationale_for(match, event, service, action_type, confidence),
        collateral_scope=collateral_scope_for(service, services, match, action_type),
        evidence={
            "event_id": event.event_id,
            "event_target_name": match.event_target.name,
            "matched_endpoint": match.endpoint.name,
            "matched_service_ids": match.all_service_ids or [service.id],
            "attack_classification": classify_attack_context(event),
            "event_observed_bps": match.event_target.observed_bps,
            "event_observed_pps": match.event_target.observed_pps,
            "event_baseline_bps": match.event_target.baseline_bps,
            "event_baseline_pps": match.event_target.baseline_pps,
            "service_traffic_baseline": dump_optional_model(service.traffic_baseline),
            "signal_metadata": {
                "telemetry_source": event.signals.telemetry_source,
                "collector_type": event.signals.collector_type,
                "sampling_window_seconds": event.signals.sampling_window_seconds,
                "sample_size": event.signals.sample_size,
                "evidence_age_seconds": event.signals.evidence_age_seconds,
                "signal_confidence": event.signals.signal_confidence.value if event.signals.signal_confidence else None,
            },
            "path_anomalies": event.signals.path_anomalies,
            "top_source_prefixes_advisory": event.signals.top_source_prefixes,
            "provider_actions_already_active": event.provider_actions_already_active,
            "service_owner": service.owner,
            "service_approver": service.approver,
            "business_process": service.business_process,
            "rollback_control": dump_optional_model(service.rollback_control),
        },
    )


def make_monitor_only_action(
    event: DdosEvent,
    generated_at: datetime,
    config: CompilerConfig,
    pack: PolicyPack,
    policy_pack_supplied: bool,
    *,
    event_target_name: str,
    target_ip: str,
    target_protocol: str,
    target_ports: list[int] | None,
    reason_codes: list[str],
    reason_text: list[str],
    safety_notes: list[str],
    business_impact: list[str],
    suggested_question: str,
    evidence: dict[str, object],
    approval_required: bool = False,
    risk_level: RiskLevel = RiskLevel.LOW,
) -> BrownoutAction:
    ttl = min(config.default_ttl_minutes, pack.ttl.default_minutes, config.max_ttl_minutes)
    codes = list(reason_codes)
    codes.extend(
        [
            "TARGET_UNDER_ATTACK",
            "TEMPORARY_TTL_APPLIED",
            "REVIEW_ONLY_MODE",
            "NO_LIVE_ENFORCEMENT",
            "USER_POLICY_PACK_USED" if policy_pack_supplied else "POLICY_PACK_DEFAULT_USED",
        ]
    )
    if event.confidence == Confidence.LOW:
        codes.append("LOW_CONFIDENCE_EVENT")
    if event.attack_class.value == "UNKNOWN":
        codes.append("UNKNOWN_ATTACK_CLASS")
    impact = list(business_impact)
    impact.append("Business process: unmapped or source-prefix review. Owner: human review required. Users: legitimate users may be affected by unsupported external action. Revenue impact: cannot be quantified without service ownership. SLO: not supplied. Customer tiers: not supplied.")
    impact.append("No temporary policy change is made by this monitor-only review action.")
    return BrownoutAction(
        action_id="pending",
        action_type=ActionType.MONITOR_ONLY,
        service_id="unmapped_event_target",
        service_display_name="Unmapped event target",
        service_priority=Priority.P4,
        brownout_mode=BrownoutMode.NO_ACTION,
        target=ActionTarget(ip=target_ip, protocol=target_protocol, ports=target_ports),
        selectors={},
        parameters={"review_only": True},
        ttl_minutes=ttl,
        expires_at=generated_at + timedelta(minutes=ttl),
        decision_required_by=generated_at + timedelta(minutes=min(ttl, 10)),
        rollback_action_id="not_required",
        approval_required=approval_required,
        risk_level=risk_level,
        confidence=event.confidence,
        reason_codes=sorted(set(codes), key=codes.index),
        reason_text=reason_text,
        safety_notes=safety_notes,
        business_impact=impact,
        suggested_operator_question=[suggested_question],
        risk_factors=["monitor_only_review_item", f"computed_risk:{risk_level.value}"],
        confidence_rationale=[f"event_confidence:{event.confidence.value}", "no_service_mapping_or_source_review_only"],
        collateral_scope={"collateral_review_required": True, "impacted_service_ids": []},
        evidence={
            "event_id": event.event_id,
            "event_target_name": event_target_name,
            "attack_classification": classify_attack_context(event),
            **evidence,
        },
    )


def monitor_actions_for_unmatched(
    event: DdosEvent,
    unmatched_names: list[str],
    generated_at: datetime,
    config: CompilerConfig,
    pack: PolicyPack,
    policy_pack_supplied: bool,
) -> list[BrownoutAction]:
    actions: list[BrownoutAction] = []
    unmatched = {name for name in unmatched_names}
    for target in event.targets:
        if target.name not in unmatched:
            continue
        actions.append(
            make_monitor_only_action(
                event,
                generated_at,
                config,
                pack,
                policy_pack_supplied,
                event_target_name=target.name,
                target_ip=target.ip,
                target_protocol=target.protocol,
                target_ports=target.ports,
                reason_codes=["UNMAPPED_ATTACK_TARGET"],
                reason_text=[
                    "The observed target in the mitigation event is not mapped to a service-priority entry.",
                    "No temporary policy change is recommended without service ownership and business priority.",
                ],
                safety_notes=[
                    "Map the target to a service-priority entry before recommending a temporary action.",
                    "Do not infer service ownership from names alone.",
                ],
                business_impact=[
                    "Business impact cannot be assessed until the target is mapped to a service owner and priority.",
                ],
                suggested_question="What service owns this observed target, and what priority should it have?",
                evidence={
                    "top_source_prefixes_advisory": event.signals.top_source_prefixes,
                    "path_anomalies": event.signals.path_anomalies,
                },
            )
        )
    return actions


def monitor_action_for_source_block_review(
    event: DdosEvent,
    generated_at: datetime,
    config: CompilerConfig,
    pack: PolicyPack,
    policy_pack_supplied: bool,
) -> BrownoutAction | None:
    if event.signals.spoofing_likely or not event.signals.top_source_prefixes:
        return None
    target = event.targets[0]
    action = make_monitor_only_action(
        event,
        generated_at,
        config,
        pack,
        policy_pack_supplied,
        event_target_name=target.name,
        target_ip=target.ip,
        target_protocol=target.protocol,
        target_ports=target.ports,
        reason_codes=["SOURCE_BLOCKING_DISABLED_BY_DEFAULT"],
        reason_text=[
            "Observed source prefixes are advisory evidence only.",
            "Source-prefix blocking remains a human review item in the MVP rather than a policy action.",
        ],
        safety_notes=[
            "Do not call an observed source prefix malicious with certainty.",
            "Review prefix breadth, spoofing likelihood, and collateral business impact before any external process considers blocking.",
        ],
        business_impact=[
            "Blocking an observed source prefix outside this compiler could affect legitimate users sharing that prefix.",
        ],
        suggested_question="Is there enough non-spoofed evidence to review observed source prefixes without broad collateral impact?",
        evidence={
            "observed_source_prefixes": event.signals.top_source_prefixes,
            "top_source_asns": event.signals.top_source_asns,
            "top_source_countries": event.signals.top_source_countries,
        },
        approval_required=True,
        risk_level=RiskLevel.HIGH,
    )
    action.selectors["observed_source_prefixes"] = event.signals.top_source_prefixes
    action.parameters["source_block_review_only"] = True
    return action


def sorted_actions(actions: list[BrownoutAction]) -> list[BrownoutAction]:
    return sorted(
        actions,
        key=lambda action: (
            PRIORITY_ORDER[action.service_priority.value],
            RISK_SORT[action.risk_level],
            action.service_id,
            action.action_type.value,
            action.target.ip,
        ),
    )


def assign_action_ids(actions: list[BrownoutAction]) -> list[BrownoutAction]:
    assigned: list[BrownoutAction] = []
    for index, action in enumerate(actions, start=1):
        assigned.append(
            action.model_copy(
                update={
                    "action_id": f"act_{index:03d}",
                    "rollback_action_id": f"rb_{index:03d}",
                }
            )
        )
    return assigned


def action_group_key(action: BrownoutAction) -> tuple[str, str, str, tuple[int | str, ...]]:
    return (action.service_id, action.target.ip, action.target.protocol, tuple(action.target.ports or []))


def action_group_role(action: BrownoutAction) -> tuple[str, bool]:
    if action.action_type in {ActionType.MONITOR_ONLY, ActionType.NO_ACTION}:
        return "monitor_or_no_change", False
    if action.action_type == ActionType.ALLOW_TRUSTED_SOURCES:
        return "preserve_trusted_access", False
    if action.action_type == ActionType.PRIORITIZE:
        return "priority_overlay", False
    if action.action_type in {ActionType.RATE_LIMIT, ActionType.RATE_LIMIT_UNTRUSTED, ActionType.DEPRIORITIZE, ActionType.CHALLENGE}:
        return "traffic_reduction_candidate", True
    return "high_impact_alternative", True


def assign_action_groups(actions: list[BrownoutAction]) -> tuple[list[BrownoutAction], list[dict[str, object]]]:
    grouped: dict[tuple[str, str, str, tuple[int | str, ...]], list[BrownoutAction]] = {}
    for action in actions:
        grouped.setdefault(action_group_key(action), []).append(action)
    key_to_group_id = {key: f"ag_{index:03d}" for index, key in enumerate(sorted(grouped), start=1)}
    updated: list[BrownoutAction] = []
    groups: list[dict[str, object]] = []
    for key in sorted(grouped):
        group_actions = grouped[key]
        group_id = key_to_group_id[key]
        exclusive_types = []
        cumulative_types = []
        action_ids = []
        for action in group_actions:
            role, exclusive = action_group_role(action)
            if exclusive:
                exclusive_types.append(action.action_type.value)
            else:
                cumulative_types.append(action.action_type.value)
            action_ids.append(action.action_id)
            updated.append(
                action.model_copy(
                    update={
                        "action_group_id": group_id,
                        "action_group_role": role,
                        "action_group_exclusive": exclusive,
                    }
                )
            )
        groups.append(
            {
                "action_group_id": group_id,
                "service_id": key[0],
                "target": {"ip": key[1], "protocol": key[2], "ports": list(key[3])},
                "action_ids": action_ids,
                "cumulative_action_types": sorted(set(cumulative_types)),
                "exclusive_or_staged_action_types": sorted(set(exclusive_types)),
                "operator_guidance": "Review cumulative preserve/priority actions separately from mutually exclusive or staged traffic-reduction alternatives.",
            }
        )
    return sorted(updated, key=lambda action: int(action.action_id.split("_")[1])), groups


def approval_bundle_for(actions: list[BrownoutAction]) -> dict[str, object]:
    approvals = []
    for action in actions:
        if not action.approval_required and action.risk_level not in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            continue
        approvals.append(
            {
                "action_id": action.action_id,
                "action_group_id": action.action_group_id,
                "service_id": action.service_id,
                "action_type": action.action_type.value,
                "risk_level": action.risk_level.value,
                "approver": action.approver,
                "approval_metadata": action.approval_metadata,
                "decision_required_by": action.decision_required_by.isoformat().replace("+00:00", "Z") if action.decision_required_by else None,
                "approval_status": "PENDING_OPERATOR_DECISION",
                "evidence_required": ["approval timestamp", "approver identity", "operator decision", "rollback owner acknowledgement"],
            }
        )
    return {
        "approval_bundle_version": 1,
        "approval_required": bool(approvals),
        "approvals": approvals,
    }


def source_evidence_review_for(event: DdosEvent) -> dict[str, object]:
    return {
        "source_evidence_review_version": 1,
        "source_prefixes_are_advisory": bool(event.signals.top_source_prefixes),
        "spoofing_likely": event.signals.spoofing_likely,
        "observed_source_prefixes": event.signals.top_source_prefixes,
        "top_source_asns": event.signals.top_source_asns,
        "top_source_countries": event.signals.top_source_countries,
        "telemetry_source": event.signals.telemetry_source,
        "collector_type": event.signals.collector_type,
        "sampling_window_seconds": event.signals.sampling_window_seconds,
        "sample_size": event.signals.sample_size,
        "evidence_age_seconds": event.signals.evidence_age_seconds,
        "operator_question": "Is the source evidence current, non-spoofed, narrow enough, and business-reviewed before any external source action is considered?",
    }


def executive_summary_for(actions: list[BrownoutAction], warnings: list[str], blockers: list[str]) -> dict[str, object]:
    owner_counts: dict[str, int] = {}
    enforcement_counts: dict[str, int] = {}
    business_counts: dict[str, int] = {}
    for action in actions:
        owner_counts[action.owner or "unspecified"] = owner_counts.get(action.owner or "unspecified", 0) + 1
        business_counts[action.business_process or "unspecified"] = business_counts.get(action.business_process or "unspecified", 0) + 1
        for point in action.collateral_scope.get("enforcement_points", []) if action.collateral_scope else []:
            enforcement_counts[str(point)] = enforcement_counts.get(str(point), 0) + 1
    return {
        "executive_summary_version": 1,
        "total_actions": len(actions),
        "high_or_critical_actions": sum(1 for action in actions if action.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}),
        "approval_required_actions": sum(1 for action in actions if action.approval_required),
        "warnings": warnings,
        "blockers": blockers,
        "actions_by_owner": dict(sorted(owner_counts.items())),
        "actions_by_business_process": dict(sorted(business_counts.items())),
        "actions_by_enforcement_point": dict(sorted(enforcement_counts.items())),
    }


def handoff_bundle_for(actions: list[BrownoutAction]) -> dict[str, object]:
    return {
        "handoff_bundle_version": 1,
        "included_artifacts": [
            "brownout_plan.yml",
            "actions.csv",
            "actions_enriched.csv when generated",
            "rollback_plan.yml",
            "summary.json",
            "decision_trace.json when generated",
            "markdown summary when generated",
            "fingerprints.json when generated",
            "redaction audit when generated",
        ],
        "operator_handoff_checks": [
            "Confirm each approval-required action has an operator decision.",
            "Confirm rollback owner acknowledges each non-monitor temporary action.",
            "Confirm evidence is attached before incident review closure.",
        ],
        "action_ids": [action.action_id for action in actions],
    }


def assumptions_for(event: DdosEvent, policy_pack_supplied: bool, allow_source_blocks: bool, allow_null_route: bool) -> list[str]:
    assumptions = [
        "Compiler did not verify live device state.",
        "Review package is not live enforcement.",
        "Temporary actions require human review before use.",
    ]
    if event.signals.spoofing_likely:
        assumptions.append("Source prefixes are advisory because spoofing_likely=true.")
    elif event.signals.top_source_prefixes:
        assumptions.append("Observed source prefixes are advisory and not treated as malicious with certainty.")
    if not policy_pack_supplied:
        assumptions.append("Built-in conservative policy pack was used.")
    if not allow_source_blocks:
        assumptions.append("Source-prefix blocking is disabled by default.")
    if not allow_null_route:
        assumptions.append("Temporary null-route recommendation is disabled by default.")
    if event.provider_actions_already_active:
        assumptions.append("The event reports mitigation actions already active outside this compiler.")
    return assumptions


def decision_trace_for_actions(actions: list[BrownoutAction], pack: PolicyPack) -> list[dict[str, object]]:
    trace: list[dict[str, object]] = []
    for action in actions:
        preferences = [item.value for item in pack.action_preferences.get(action.service_priority, [])]
        rank = action.parameters.get("policy_preference_rank")
        skipped_lower = preferences[int(rank) :] if isinstance(rank, int) and rank < len(preferences) else []
        trace.append(
            {
                "action_id": action.action_id,
                "action_group_id": action.action_group_id,
                "action_group_role": action.action_group_role,
                "action_group_exclusive": action.action_group_exclusive,
                "service_id": action.service_id,
                "selected_action": action.action_type.value,
                "policy_preference_rank": rank,
                "policy_preferences": preferences,
                "policy_preference_status": "ranked_in_policy_pack" if isinstance(rank, int) else "allowed_by_service_policy_not_ranked_in_pack",
                "skipped_lower_preference_actions": skipped_lower,
                "safety_gates_applied": action.reason_codes,
                "risk_factors": action.risk_factors,
                "confidence_rationale": action.confidence_rationale,
                "collateral_scope": action.collateral_scope,
                "decision_basis": action.reason_text,
                "review_only": True,
            }
        )
    return trace


def compile_plan_objects(
    event: DdosEvent,
    services: ServicePriorityFile,
    config: CompilerConfig,
    pack: PolicyPack,
    policy_pack_supplied: bool,
    incident_id: str,
    generated_at: datetime,
    strict: bool = False,
    allow_null_route: bool = False,
    allow_source_blocks: bool = False,
    allow_admin_lockdown: bool = False,
    max_actions: int | None = None,
) -> tuple[BrownoutPlan, object, object]:
    validation = combine_validation(
        validate_event(event, strict=strict),
        validate_service_priority(services, strict=strict, fail_on_p0_shed=config.fail_on_p0_shed),
    )
    matches, unmatched, match_validation = match_event_targets(
        event,
        services,
        strict=strict,
        fail_on_unmatched=config.fail_on_unmatched_event_targets,
    )
    validation.extend(match_validation)
    if allow_source_blocks and event.signals.spoofing_likely:
        validation.warnings.append("SPOOFING_LIKELY_SOURCE_BLOCKS_SKIPPED")
    if allow_source_blocks and event.signals.top_source_prefixes:
        validation.warnings.append("SOURCE_PREFIXES_ADVISORY_ONLY")
    context = classify_attack_context(event)
    actions: list[BrownoutAction] = []
    for match in matches:
        for action_type in candidate_action_types(
            match,
            services,
            pack,
            context,
            allow_null_route=allow_null_route,
            allow_admin_lockdown=allow_admin_lockdown,
            validation=validation,
        ):
            action = make_action(action_type, match, event, services, config, pack, policy_pack_supplied, generated_at, validation)
            if action is not None:
                actions.append(action)
    actions.extend(monitor_actions_for_unmatched(event, unmatched, generated_at, config, pack, policy_pack_supplied))
    if allow_source_blocks:
        source_review_action = monitor_action_for_source_block_review(event, generated_at, config, pack, policy_pack_supplied)
        if source_review_action is not None:
            actions.append(source_review_action)

    actions = sorted_actions(actions)
    action_limit = max_actions or config.max_actions
    if len(actions) > action_limit:
        validation.warnings.append("ACTION_LIMIT_REACHED")
        actions = actions[:action_limit]
    actions = assign_action_ids(actions)
    actions, action_groups = assign_action_groups(actions)

    if strict and any(action.approval_required for action in actions):
        validation.blockers.append("APPROVAL_REQUIRED_ACTION_PRESENT")
    if any(action.approval_required for action in actions):
        validation.warnings.append("APPROVAL_REQUIRED_ACTION_PRESENT")
    validation.warnings.append("REVIEW_ONLY_OUTPUT")
    validation.warnings = sorted(set(validation.warnings))
    validation.blockers = sorted(set(validation.blockers))

    expires_at = max((action.expires_at for action in actions), default=generated_at)
    plan = BrownoutPlan(
        incident_id=incident_id,
        event_id=event.event_id,
        generated_at=generated_at,
        expires_at=expires_at,
        action_count=len(actions),
        assumptions=assumptions_for(event, policy_pack_supplied, allow_source_blocks, allow_null_route),
        warnings=validation.warnings,
        blockers=validation.blockers,
        blocker_details=validation.blocker_details,
        action_groups=action_groups,
        approval_bundle=approval_bundle_for(actions),
        source_evidence_review=source_evidence_review_for(event),
        executive_summary=executive_summary_for(actions, validation.warnings, validation.blockers),
        handoff_bundle=handoff_bundle_for(actions),
        decision_trace=decision_trace_for_actions(actions, pack),
        actions=actions,
    )
    rollback_plan = make_rollback_plan(incident_id, event.event_id, generated_at, actions)
    summary = build_summary(
        incident_id=incident_id,
        event_id=event.event_id,
        event_target_count=len(event.targets),
        service_group_count=len(services.service_groups),
        matched_service_count=len({match.service.id for match in matches}),
        unmatched_event_target_count=len(unmatched),
        actions=actions,
        warnings=validation.warnings,
        blockers=validation.blockers,
    )
    return plan, rollback_plan, summary


def _artifact_path(explicit: str | Path | None, summary_path: str | Path, filename: str) -> Path:
    if explicit is not None:
        return Path(explicit)
    return Path(summary_path).with_name(filename)


def _write_decision_artifacts(
    options: CompileOptions,
    plan: BrownoutPlan,
    rollback_plan: object,
    summary: object,
    *,
    service_names: list[str],
) -> tuple[dict[str, object], dict[str, Path]]:
    decision_brief = build_decision_brief(plan, rollback_plan, summary)
    paths = {
        "decision_brief": _artifact_path(options.decision_brief, options.summary, "decision_brief.json"),
        "decision_brief_markdown": _artifact_path(options.decision_brief_markdown, options.summary, "decision_brief.md"),
        "operator_queue": _artifact_path(options.operator_queue, options.summary, "operator_queue.csv"),
        "approval_queue": _artifact_path(options.approval_queue, options.summary, "approval_queue.csv"),
        "rollback_clock": _artifact_path(options.rollback_clock, options.summary, "rollback_clock.json"),
        "blocked_actions": _artifact_path(options.blocked_actions, options.summary, "blocked_actions.json"),
    }
    write_decision_brief_json(paths["decision_brief"], decision_brief, redact=options.redact, service_names=service_names)
    write_decision_brief_markdown(paths["decision_brief_markdown"], decision_brief, redact=options.redact, service_names=service_names)
    write_operator_queue_csv(paths["operator_queue"], decision_brief, redact=options.redact, service_names=service_names)
    write_approval_queue_csv(paths["approval_queue"], decision_brief, redact=options.redact, service_names=service_names)
    write_rollback_clock_json(paths["rollback_clock"], decision_brief, redact=options.redact, service_names=service_names)
    write_blocked_actions_json(paths["blocked_actions"], decision_brief, redact=options.redact, service_names=service_names)
    return decision_brief, paths


def compile_from_paths(options: CompileOptions) -> CompileResult:
    config = load_config(options.config_path)
    pack, pack_validation, supplied = load_policy_pack(options.policy_pack_path)
    event = load_event(options.event_path)
    services = load_service_priority(options.services_path)
    if pack is None:
        raise ValueError("; ".join(pack_validation.blockers))
    incident_id = options.incident_id or f"INC-{event.event_id}"
    generated_at = parse_now(options.now)
    plan, rollback_plan, summary = compile_plan_objects(
        event,
        services,
        config,
        pack,
        supplied,
        incident_id,
        generated_at,
        strict=options.strict,
        allow_null_route=options.allow_null_route,
        allow_source_blocks=options.allow_source_blocks,
        allow_admin_lockdown=options.allow_admin_lockdown,
        max_actions=options.max_actions,
    )
    if pack_validation.warnings:
        plan.warnings = sorted(set(plan.warnings + pack_validation.warnings))
        summary.warnings = sorted(set(summary.warnings + pack_validation.warnings))
    if pack_validation.blockers:
        plan.blockers = sorted(set(plan.blockers + pack_validation.blockers))
        summary.blockers = sorted(set(summary.blockers + pack_validation.blockers))
        summary.lint_status = "FAIL"
    if options.strict and plan.blockers:
        raise ValueError("; ".join(plan.blockers))
    service_names = sorted({name for action in plan.actions for name in (action.service_id, action.service_display_name or action.service_id) if name})
    write_yaml(options.output_plan, plan, redact=options.redact, service_names=service_names)
    write_actions_csv(options.output_actions, plan.actions, redact=options.redact)
    write_yaml(options.output_rollback, rollback_plan, redact=options.redact, service_names=service_names)
    write_json(options.summary, summary, redact=options.redact, service_names=service_names)
    decision_brief, decision_artifacts = _write_decision_artifacts(
        options,
        plan,
        rollback_plan,
        summary,
        service_names=service_names,
    )
    return CompileResult(
        plan=plan,
        rollback_plan=rollback_plan,
        summary=summary,
        decision_brief=decision_brief,
        decision_artifacts=decision_artifacts,
        warnings=plan.warnings,
        blockers=plan.blockers,
    )
