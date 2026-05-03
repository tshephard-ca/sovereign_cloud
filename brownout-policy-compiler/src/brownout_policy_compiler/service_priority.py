from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import BrownoutMode, Priority, ServicePriorityFile, ValidationResult


def load_service_priority(path: str | Path) -> ServicePriorityFile:
    data = yaml.safe_load(Path(path).read_text()) or {}
    return ServicePriorityFile.model_validate(data)


def try_load_service_priority(path: str | Path) -> tuple[ServicePriorityFile | None, ValidationResult]:
    result = ValidationResult()
    try:
        return load_service_priority(path), result
    except (ValidationError, ValueError, yaml.YAMLError) as exc:
        result.blockers.append("SERVICE_PRIORITY_INVALID")
        result.warnings.append(str(exc))
        return None, result


def validate_service_priority(
    services: ServicePriorityFile,
    strict: bool = False,
    fail_on_p0_shed: bool = True,
) -> ValidationResult:
    result = ValidationResult()
    if not services.service_groups:
        result.blockers.append("NO_SERVICE_GROUPS")

    def warn_or_block(code: str) -> None:
        result.warnings.append(code)
        if strict:
            result.blockers.append(code)

    org = services.organization
    if not org.sector or not org.operating_model or not org.regions or not org.customer_segments:
        warn_or_block("ORGANIZATION_PROFILE_INCOMPLETE")
    if not org.critical_operating_periods:
        result.warnings.append("ORGANIZATION_CRITICAL_PERIODS_MISSING")

    trusted_groups = set(services.trusted_sources.keys())
    today = date.today()
    for group in services.trusted_sources.values():
        if not group.review_owner or group.last_reviewed_at is None or group.review_cadence_days is None:
            warn_or_block("TRUSTED_SOURCE_REVIEW_METADATA_MISSING")
        elif group.last_reviewed_at + timedelta(days=group.review_cadence_days) < today:
            warn_or_block("TRUSTED_SOURCE_REVIEW_STALE")
        if not group.exception_process or not group.emergency_override_process:
            result.warnings.append("TRUSTED_SOURCE_PROCESS_METADATA_MISSING")

    service_ids = {service.id for service in services.service_groups}
    endpoint_ip_counts: dict[str, int] = {}
    for service in services.service_groups:
        for endpoint in service.endpoints:
            endpoint_ip_counts[endpoint.ip] = endpoint_ip_counts.get(endpoint.ip, 0) + 1

    for service in services.service_groups:
        if service.priority == Priority.P0 and service.brownout_mode == BrownoutMode.SHED:
            if fail_on_p0_shed or strict:
                result.blockers.append("P0_SERVICE_MARKED_SHED")
            else:
                result.warnings.append("P0_SERVICE_MARKED_SHED")
        if not service.owner or not service.business_process:
            warn_or_block("SERVICE_OWNERSHIP_METADATA_MISSING")
        if not service.criticality_rationale or service.rto_minutes is None or service.rpo_minutes is None or not service.slo:
            warn_or_block("SERVICE_CRITICALITY_METADATA_MISSING")
        if not service.user_population or not service.revenue_impact:
            result.warnings.append("SERVICE_BUSINESS_IMPACT_METADATA_MISSING")
        if service.approval_required and (not service.approver or service.approval_metadata is None):
            warn_or_block("APPROVAL_METADATA_MISSING")
        if service.rollback_required and (not service.rollback_owner or service.rollback_control is None or not service.rollback_control.verification_steps):
            warn_or_block("ROLLBACK_CONTROL_MISSING")
        if service.traffic_baseline is None:
            result.warnings.append("SERVICE_TRAFFIC_BASELINE_MISSING")
        for dependency in service.depends_on:
            if dependency.service_id not in service_ids:
                warn_or_block("SERVICE_DEPENDENCY_MISSING")
        for group in service.trusted_source_groups:
            if group not in trusted_groups:
                if strict:
                    result.blockers.append("TRUSTED_SOURCE_REQUIRED_BUT_MISSING")
                result.warnings.append("TRUSTED_SOURCE_GROUP_MISSING")
        trusted_requirement = (service.model_extra or {}).get("trusted_source_requirement", "UNKNOWN")
        if not service.trusted_source_groups and trusted_requirement != "NOT_APPLICABLE":
            result.warnings.append("SERVICE_HAS_NO_TRUSTED_SOURCES")
        for endpoint in service.endpoints:
            if endpoint.exposure is None or not endpoint.enforcement_points:
                warn_or_block("ENDPOINT_OPERATIONAL_METADATA_MISSING")
            if endpoint_ip_counts.get(endpoint.ip, 0) > 1 and endpoint.shared_endpoint_group is None:
                warn_or_block("SHARED_ENDPOINT_GROUP_MISSING")
    result.warnings = sorted(set(result.warnings))
    result.blockers = sorted(set(result.blockers))
    return result
