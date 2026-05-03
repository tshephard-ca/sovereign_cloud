"""Aggregate query-level evidence into observed prerequisites."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import ObservedPrerequisite, QueryEvidence
from .scoring import CONFIDENCE_ORDER, max_confidence


def aggregate_evidence(evidence: list[QueryEvidence], config: dict[str, Any]) -> list[ObservedPrerequisite]:
    grouped: dict[tuple[str, str, str, str], list[QueryEvidence]] = defaultdict(list)
    for item in evidence:
        key = (
            item.category,
            item.prerequisite_target or item.prerequisite_name,
            item.prerequisite_target_ip,
            "role" if item.role_level else "target",
        )
        grouped[key].append(item)

    observations: list[ObservedPrerequisite] = []
    for _, items in grouped.items():
        first = items[0]
        max_source_rows = int(config.get("max_source_rows_per_finding", 20))
        protected_systems = _unique([item.protected_system for item in items if item.protected_system])
        reason_codes = _unique([code for item in items for code in item.reason_codes])
        missing_data = _unique([field for item in items for field in item.missing_data])
        confidence = max_confidence([item.confidence for item in items])
        weak_heuristic = any(item.weak_heuristic for item in items)
        if len(protected_systems) >= 2:
            reason_codes.append("MULTIPLE_PROTECTED_SYSTEMS_OBSERVED")
        if weak_heuristic and confidence == "LOW" and len(protected_systems) >= int(config.get("high_confidence_min_clients", 2)):
            confidence = "MEDIUM"
        if len(items) < int(config.get("min_query_count", 2)) and first.evidence_source == "dns_query_log":
            reason_codes.append("LOW_QUERY_COUNT")
            if weak_heuristic and CONFIDENCE_ORDER[confidence] > CONFIDENCE_ORDER["LOW"]:
                confidence = "LOW"
        observations.append(
            ObservedPrerequisite(
                category=first.category,
                prerequisite_name=first.prerequisite_name,
                prerequisite_target=first.prerequisite_target,
                prerequisite_target_ip=first.prerequisite_target_ip,
                confidence=confidence,  # type: ignore[arg-type]
                observed_query_count=len(items),
                observed_by_protected_systems=len(protected_systems),
                protected_systems=protected_systems,
                example_qnames=_unique([item.qname for item in items if item.qname]),
                example_answer_names=_unique([name for item in items for name in item.answer_names]),
                example_answer_ips=_unique([ip for item in items for ip in item.answer_ips]),
                evidence_source=_unique([item.evidence_source for item in items])[0],
                reason_codes=reason_codes,
                missing_data=missing_data,
                notes=_unique([note for item in items for note in item.notes]),
                source_rows=_unique_limited((row for item in items for row in item.source_rows), max_source_rows),
                role_level=any(item.role_level for item in items),
                known_prereq=any(item.known_prereq for item in items),
                required_in_recovery_set=any(item.required_in_recovery_set for item in items),
                weak_heuristic=weak_heuristic,
                internal=any(item.internal for item in items),
            )
        )
    return sorted(observations, key=lambda obs: (obs.category, obs.prerequisite_target or obs.prerequisite_name, obs.prerequisite_target_ip))


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _unique_limited(values: object, limit: int) -> list[str]:
    result: list[str] = []
    for value in values:  # type: ignore[operator]
        if value and value not in result:
            result.append(value)
        if len(result) >= limit:
            break
    return result
