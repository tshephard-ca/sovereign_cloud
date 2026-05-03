from __future__ import annotations

from .models import Confidence, DdosEvent, MatchResult, ServiceGroup, ServicePriorityFile, ValidationResult
from .validators import ip_matches, ports_overlap, protocol_matches


PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}


def match_event_targets(
    event: DdosEvent,
    services: ServicePriorityFile,
    strict: bool = False,
    fail_on_unmatched: bool = False,
) -> tuple[list[MatchResult], list[str], ValidationResult]:
    result = ValidationResult()
    matches: list[MatchResult] = []
    unmatched: list[str] = []
    for target in event.targets:
        target_matches: list[MatchResult] = []
        for service in services.service_groups:
            for endpoint in service.endpoints:
                ip_ok, cidr_match = ip_matches(target.ip, endpoint.ip)
                if not ip_ok:
                    continue
                if not protocol_matches(target.protocol, endpoint.protocol):
                    continue
                reason_codes = ["TARGET_UNDER_ATTACK", "TARGET_MATCHED_SERVICE"]
                confidence = Confidence.HIGH
                if cidr_match:
                    reason_codes.append("CIDR_ENDPOINT_MATCH")
                    confidence = Confidence.LOW
                if target.ports is None:
                    reason_codes.append("EVENT_TARGET_PORTS_MISSING")
                    confidence = Confidence.MEDIUM if confidence == Confidence.HIGH else Confidence.LOW
                elif not ports_overlap(target.ports, endpoint.ports):
                    continue
                target_matches.append(
                    MatchResult(
                        event_target=target,
                        service=service,
                        endpoint=endpoint,
                        reason_codes=reason_codes,
                        confidence=confidence,
                    )
                )
        if not target_matches:
            unmatched.append(target.name)
            result.warnings.append("UNMAPPED_ATTACK_TARGET")
            if strict or fail_on_unmatched:
                result.blockers.append("UNMAPPED_ATTACK_TARGET")
            continue
        target_matches.sort(key=lambda item: (PRIORITY_ORDER[item.service.priority.value], item.service.id))
        chosen = target_matches[0]
        all_ids = [item.service.id for item in target_matches]
        chosen.all_service_ids = all_ids
        if len(target_matches) > 1:
            result.warnings.append("TARGET_MATCHES_MULTIPLE_SERVICES")
            chosen.reason_codes.append("TARGET_MATCHES_MULTIPLE_SERVICES")
        matches.append(chosen)
    result.warnings = sorted(set(result.warnings))
    result.blockers = sorted(set(result.blockers))
    return matches, unmatched, result


def services_sharing_destination(service: ServiceGroup, services: ServicePriorityFile, destination_ip: str) -> list[str]:
    sharing: list[str] = []
    for other in services.service_groups:
        for endpoint in other.endpoints:
            try:
                matches, _ = ip_matches(destination_ip, endpoint.ip)
            except ValueError:
                matches = False
            if matches:
                sharing.append(other.id)
                break
    return sorted(set(sharing))

