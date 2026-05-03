"""Pipeline orchestration, recovery-set matching, and finding generation."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from . import __version__
from .answer_map import enrich_dns_rows_with_answer_map, load_answer_map
from .backup_inventory import parse_backup_inventory
from .classify_prereqs import aggregate_evidence
from .classify_queries import classify_dns_query
from .client_mapping import ClientMapper
from .config import load_config
from .dns_log import filter_dns_window, parse_dns_log
from .known_prereqs import load_known_prereqs
from .models import Finding, ObservedPrerequisite, QueryEvidence, RecoverySet, RecoverySetMatch, Summary, SUPPORTED_CATEGORIES
from .normalize import compact_join, infer_internal_domains, normalize_fqdn, short_name
from .recovery_set import build_recovery_set, role_tag_present, system_display_name
from .resolver_hints import load_resolver_hints
from .scoring import sort_severity
from .support_files import load_accepted_risks, load_recovery_set_metadata, matching_accepted_risk


class AnalysisResult(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    observed: list[ObservedPrerequisite] = Field(default_factory=list)
    summary: Summary
    warnings: list[str] = Field(default_factory=list)


def analyze_inputs(
    *,
    backup_inventory: str | Path,
    dns_log: str | Path,
    recovery_set_name: str | None = None,
    known_prereqs_path: str | Path | None = None,
    resolver_hints_path: str | Path | None = None,
    answer_map_path: str | Path | None = None,
    accepted_risks_path: str | Path | None = None,
    recovery_sets_path: str | Path | None = None,
    config_path: str | Path | None = None,
    policy_pack: str | None = None,
    window_hours: int | None = None,
    strict: bool = False,
    include_unmapped_clients: bool = False,
    include_external: bool | None = None,
    min_query_count: int | None = None,
) -> AnalysisResult:
    config = load_config(config_path, policy_pack=policy_pack)
    if window_hours is not None:
        config["window_hours"] = window_hours
    if min_query_count is not None:
        config["min_query_count"] = min_query_count
    if include_external is None:
        include_external = bool(config.get("include_external_by_default", False))

    warnings: list[str] = []
    assumptions: list[str] = []
    backup = _cached_parse_backup_inventory(backup_inventory, strict=strict)
    warnings.extend(backup.warnings)
    recovery_set = build_recovery_set(backup.rows, recovery_set_name=recovery_set_name, strict=strict)
    warnings.extend(recovery_set.warnings)
    if strict and not backup.protected_systems:
        raise ValueError("zero protected systems found in backup inventory")
    if strict and not recovery_set.systems:
        raise ValueError("zero recovery-set systems found")

    dns = _cached_parse_dns_log(dns_log, strict=strict)
    warnings.extend(dns.warnings)
    answer_entries = _cached_load_answer_map(answer_map_path)
    dns_rows, answer_map_enriched = enrich_dns_rows_with_answer_map(dns.rows, answer_entries)
    if answer_map_enriched:
        warnings.append("ANSWER_MAP_ENRICHED")
    dns_rows_in_window, window_warnings = filter_dns_window(dns_rows, int(config.get("window_hours", 24)))
    warnings.extend(window_warnings)

    known = _cached_load_known_prereqs(known_prereqs_path)
    if known.internal_domains:
        internal_domains = known.internal_domains
    else:
        internal_domains = infer_internal_domains(system.fqdn for system in backup.protected_systems if system.fqdn)
        if internal_domains:
            warnings.append("INTERNAL_DOMAINS_INFERRED")
            assumptions.append("internal domains inferred from protected-system FQDNs")
        else:
            warnings.append("INTERNAL_DOMAINS_INFERRED")
            assumptions.append("internal domains could not be declared or inferred")

    resolver_hints, resolver_warnings = _cached_load_resolver_hints(resolver_hints_path, strict=strict)
    warnings.extend(resolver_warnings)
    accepted_risks = load_accepted_risks(accepted_risks_path)
    recovery_set_metadata = load_recovery_set_metadata(recovery_sets_path)
    selected_metadata = recovery_set_metadata.get(recovery_set.name)
    if recovery_sets_path and not selected_metadata:
        warnings.append("RECOVERY_SET_METADATA_NOT_FOUND")

    mapper = ClientMapper(backup.protected_systems)
    mapped_clients: set[str] = set()
    unmapped_clients: set[str] = set()
    evidence: list[QueryEvidence] = []
    for row in dns_rows_in_window:
        mapped = mapper.map_query(row)
        identity = row.client_ip or row.client_name or f"dns:{row.source_row}"
        if mapped.system:
            mapped_clients.add(identity)
        else:
            unmapped_clients.add(identity)
            if "UNMAPPED_DNS_CLIENT" not in warnings:
                warnings.append("UNMAPPED_DNS_CLIENT")
            if not include_unmapped_clients:
                continue
        evidence.extend(
            classify_dns_query(
                row,
                mapped,
                known_prereqs=known,
                internal_domains=internal_domains,
                include_external=include_external,
            )
        )
    if strict and not mapped_clients:
        raise ValueError("zero DNS clients mapped to protected systems")

    resolver_evidence, resolver_identity_known = _resolver_evidence(resolver_hints, dns_rows_in_window)
    evidence.extend(resolver_evidence)
    if not resolver_identity_known:
        warnings.append("DNS_RESOLVER_IDENTITY_UNKNOWN")

    matched_observed, findings = _observed_and_findings_from_evidence(evidence, recovery_set, config, accepted_risks=accepted_risks)
    accepted_risk_count = sum(1 for item in matched_observed if "ACCEPTED_RISK_APPLIED" in item.reason_codes)
    if accepted_risk_count:
        warnings.append("ACCEPTED_RISK_APPLIED")
    findings = sorted(findings, key=lambda item: (sort_severity(item.severity), item.category, item.prerequisite_name, item.prerequisite_target, item.prerequisite_target_ip))
    summary = _build_summary(
        findings,
        matched_observed,
        recovery_set,
        warnings,
        assumptions,
        backup_rows=len(backup.rows),
        dns_rows=len(dns.rows),
        dns_rows_in_window=len(dns_rows_in_window),
        dns_rows_all=dns_rows,
        dns_rows_window=dns_rows_in_window,
        backup_inventory_rows_detail=backup.rows,
        protected_systems=len(backup.protected_systems),
        mapped_clients=len(mapped_clients),
        unmapped_clients=len(unmapped_clients),
        resolver_identity_known=resolver_identity_known,
        config=config,
        answer_map_enriched=answer_map_enriched,
        accepted_risk_count=accepted_risk_count,
        recovery_set_metadata=selected_metadata.model_dump() if selected_metadata else {},
        input_paths=[backup_inventory, dns_log, known_prereqs_path, resolver_hints_path, answer_map_path, accepted_risks_path, recovery_sets_path, config_path],
        policy_pack=policy_pack,
    )
    return AnalysisResult(findings=findings, observed=matched_observed, summary=summary, warnings=_unique(warnings))


def _observed_and_findings_from_evidence(
    evidence: list[QueryEvidence],
    recovery_set: RecoverySet,
    config: dict[str, Any],
    *,
    accepted_risks: list[Any] | None = None,
) -> tuple[list[ObservedPrerequisite], list[Finding]]:
    observed = _deduplicate_observations(aggregate_evidence(evidence, config))
    matched_observed: list[ObservedPrerequisite] = []
    for observation in observed:
        match = match_recovery_set(observation, recovery_set)
        observation.present_in_recovery_set = match.present
        observation.match_basis = match.match_basis
        if match.present:
            _enrich_observation_from_match(observation, match, recovery_set)
        if match.present:
            _append_reason(observation.reason_codes, "TARGET_PRESENT_IN_RECOVERY_SET")
            if match.match_basis:
                _append_reason(observation.reason_codes, match.match_basis)
        else:
            _append_reason(observation.reason_codes, "NO_RECOVERY_SET_MATCH")
            _append_missing_data_for_match(observation)
        if not observation.present_in_recovery_set and accepted_risks:
            _apply_accepted_risk(observation, accepted_risks)
        if not observation.required_in_recovery_set:
            _append_reason(observation.reason_codes, "OPTIONAL_PREREQ_OBSERVED")
        matched_observed.append(observation)
    matched_observed = _deduplicate_observations(matched_observed)
    findings = [_finding_for_observation(observation, recovery_set.name, config) for observation in matched_observed]
    findings = sorted(findings, key=lambda item: (sort_severity(item.severity), item.category, item.prerequisite_name, item.prerequisite_target, item.prerequisite_target_ip))
    return matched_observed, findings


def match_recovery_set(observation: ObservedPrerequisite, recovery_set: RecoverySet) -> RecoverySetMatch:
    candidate_ips = _unique([observation.prerequisite_target_ip] + observation.example_answer_ips)
    for ip in candidate_ips:
        for system in recovery_set.systems:
            if ip and ip in system.ip_addresses:
                return RecoverySetMatch(present=True, match_basis="IP_MATCH", matched_systems=[system_display_name(system)])

    candidate_names = _unique(
        [observation.prerequisite_target, observation.prerequisite_name]
        + observation.example_answer_names
        + observation.example_qnames
    )
    normalized_names = [normalize_fqdn(name) for name in candidate_names if normalize_fqdn(name)]
    for name in normalized_names:
        for system in recovery_set.systems:
            if system.fqdn and name == system.fqdn:
                return RecoverySetMatch(present=True, match_basis="HOSTNAME_MATCH", matched_systems=[system_display_name(system)])
    for name in normalized_names:
        name_short = short_name(name)
        for system in recovery_set.systems:
            if name_short and system.short_name and name_short == system.short_name:
                return RecoverySetMatch(present=True, match_basis="HOSTNAME_MATCH", matched_systems=[system_display_name(system)])
    for name in normalized_names:
        for system in recovery_set.systems:
            if name in system.aliases:
                return RecoverySetMatch(present=True, match_basis="ALIAS_MATCH", matched_systems=[system_display_name(system)])
    if observation.role_level and role_tag_present(recovery_set, observation.category):
        return RecoverySetMatch(present=True, match_basis="ROLE_TAG_MATCH")
    return RecoverySetMatch(present=False, match_basis="NO_RECOVERY_SET_MATCH")


def _resolver_evidence(resolver_hints: list[Any], dns_rows: list[Any]) -> tuple[list[QueryEvidence], bool]:
    evidence: list[QueryEvidence] = []
    if resolver_hints:
        for hint in resolver_hints:
            if not hint.recovery_required:
                continue
            ips = hint.ip_addresses or [""]
            for ip in ips:
                evidence.append(
                    QueryEvidence(
                        category="dns_resolver",
                        prerequisite_name=hint.name or ip,
                        prerequisite_target=hint.name,
                        prerequisite_target_ip=ip,
                        confidence="HIGH",
                        evidence_source="resolver_hints",
                        reason_codes=[],
                        source_rows=[f"resolver_hints:{hint.source_row}"],
                        internal=True,
                    )
                )
        return evidence, True

    resolver_rows = [row for row in dns_rows if row.resolver_name or row.resolver_ip]
    if not resolver_rows:
        return [], False
    for row in resolver_rows:
        evidence.append(
            QueryEvidence(
                category="dns_resolver",
                prerequisite_name=row.resolver_name or row.resolver_ip,
                prerequisite_target=row.resolver_name,
                prerequisite_target_ip=row.resolver_ip,
                confidence="MEDIUM",
                evidence_source="dns_log_resolver_identity",
                reason_codes=[],
                source_rows=[f"dns:{row.source_row}"],
                qname=row.qname,
                internal=True,
            )
        )
    return evidence, True


def _finding_for_observation(observation: ObservedPrerequisite, recovery_set_name: str, config: dict[str, Any]) -> Finding:
    severity = _severity_for_observation(observation, config)
    finding_code = _finding_code(observation)
    reason_codes = list(observation.reason_codes)
    if finding_code not in reason_codes:
        reason_codes.insert(0, finding_code)
    return Finding(
        severity=severity,  # type: ignore[arg-type]
        confidence=observation.confidence,
        finding_code=finding_code,
        category=observation.category,
        prerequisite_name=observation.prerequisite_name,
        prerequisite_target=observation.prerequisite_target,
        prerequisite_target_ip=observation.prerequisite_target_ip,
        recovery_set=recovery_set_name,
        present_in_recovery_set=observation.present_in_recovery_set,
        match_basis=observation.match_basis,
        observed_query_count=observation.observed_query_count,
        observed_by_protected_systems=observation.observed_by_protected_systems,
        example_protected_systems=observation.protected_systems,
        example_qnames=observation.example_qnames,
        example_answer_names=observation.example_answer_names,
        example_answer_ips=observation.example_answer_ips,
        evidence_source=observation.evidence_source,
        reason_codes=_unique(reason_codes),
        suggested_action=_suggested_action(observation),
        suggested_human_question=_suggested_question(observation.category),
        missing_data=observation.missing_data,
        source_rows=observation.source_rows,
    )


def _severity_for_observation(observation: ObservedPrerequisite, config: dict[str, Any]) -> str:
    if not observation.required_in_recovery_set:
        return "INFO"
    if observation.present_in_recovery_set:
        if observation.role_level and "ANSWER_DATA_MISSING" in observation.reason_codes:
            return "REVIEW"
        return "INFO"
    if observation.category == "dns_resolver":
        return config["severity"].get("dns_resolver_missing", "CRITICAL")
    if observation.category == "directory_service":
        return config["severity"].get("directory_role_missing", "CRITICAL")
    if observation.category == "kerberos_service":
        return config["severity"].get("kerberos_role_missing", "CRITICAL")
    if observation.category == "global_catalog":
        return config["severity"].get("specific_target_missing", "CRITICAL")
    if observation.known_prereq:
        if (
            observation.confidence == "HIGH"
            and observation.observed_by_protected_systems >= int(config.get("high_confidence_min_clients", 2))
            and observation.observed_query_count >= int(config.get("repeated_observation_min_count", 5))
            and observation.category in {"database_host", "file_share", "license_server", "vpn_endpoint"}
        ):
            return config["severity"].get("known_prereq_high_volume_missing", "CRITICAL")
        return config["severity"].get("known_prereq_missing", "WARNING")
    if observation.category in {"database_host", "file_share", "license_server"} and observation.confidence in {"MEDIUM", "HIGH"} and observation.observed_by_protected_systems >= 2:
        return "CRITICAL"
    if observation.category == "time_service":
        return "REVIEW"
    if observation.confidence == "LOW":
        return "REVIEW"
    return config["severity"].get("heuristic_prereq_missing", "REVIEW")


def _finding_code(observation: ObservedPrerequisite) -> str:
    if "ACCEPTED_RISK_APPLIED" in observation.reason_codes:
        return "ACCEPTED_RISK_APPLIED"
    if not observation.required_in_recovery_set:
        return "OPTIONAL_PREREQ_OBSERVED"
    if observation.present_in_recovery_set:
        return "TARGET_PRESENT_IN_RECOVERY_SET"
    if observation.category == "dns_resolver":
        return "DNS_RESOLVER_NOT_IN_RECOVERY_SET"
    if observation.role_level and observation.category == "directory_service":
        return "DIRECTORY_SERVICE_ROLE_NOT_IN_RECOVERY_SET"
    if observation.role_level and observation.category == "kerberos_service":
        return "KERBEROS_ROLE_NOT_IN_RECOVERY_SET"
    if observation.role_level and observation.category == "global_catalog":
        return "GLOBAL_CATALOG_NOT_IN_RECOVERY_SET"
    return "SPECIFIC_TARGET_NOT_IN_RECOVERY_SET"


def _append_missing_data_for_match(observation: ObservedPrerequisite) -> None:
    if not observation.prerequisite_target_ip and not observation.example_answer_ips:
        _append_reason(observation.missing_data, "answer_ips")
    if not observation.prerequisite_target and not observation.example_answer_names and observation.role_level:
        _append_reason(observation.missing_data, "answer_names")
    if observation.role_level:
        _append_reason(observation.missing_data, "role_tags")


def _apply_accepted_risk(observation: ObservedPrerequisite, accepted_risks: list[Any]) -> None:
    risk = matching_accepted_risk(observation, accepted_risks)
    if risk is None:
        return
    observation.required_in_recovery_set = False
    _append_reason(observation.reason_codes, "ACCEPTED_RISK_APPLIED")
    if risk.id:
        observation.notes = _unique(observation.notes + [f"accepted_risk:{risk.id}"])
    if risk.reason:
        observation.notes = _unique(observation.notes + [risk.reason])


def _deduplicate_observations(observed: list[ObservedPrerequisite]) -> list[ObservedPrerequisite]:
    grouped: dict[tuple[str, str], list[ObservedPrerequisite]] = {}
    for observation in observed:
        grouped.setdefault(_observation_dedupe_key(observation), []).append(observation)
    merged: list[ObservedPrerequisite] = []
    for _, items in grouped.items():
        base = _choose_observation_base(items).model_copy(deep=True)
        base.confidence = _max_confidence([item.confidence for item in items])  # type: ignore[assignment]
        base.observed_query_count = sum(item.observed_query_count for item in items)
        base.protected_systems = _unique([value for item in items for value in item.protected_systems])
        base.observed_by_protected_systems = len(base.protected_systems)
        base.example_qnames = _unique([value for item in items for value in item.example_qnames])
        base.example_answer_names = _unique([value for item in items for value in item.example_answer_names])
        base.example_answer_ips = _unique([value for item in items for value in item.example_answer_ips])
        base.reason_codes = _unique([value for item in items for value in item.reason_codes])
        base.missing_data = _unique([value for item in items for value in item.missing_data])
        base.notes = _unique([value for item in items for value in item.notes])
        base.source_rows = _unique([value for item in items for value in item.source_rows])
        base.present_in_recovery_set = any(item.present_in_recovery_set for item in items)
        base.match_basis = _best_match_basis([item.match_basis for item in items])
        matched_phase = any(item.match_basis or item.present_in_recovery_set for item in items)
        if matched_phase and base.present_in_recovery_set:
            base.reason_codes = [code for code in base.reason_codes if code != "NO_RECOVERY_SET_MATCH"]
            _append_reason(base.reason_codes, "TARGET_PRESENT_IN_RECOVERY_SET")
        elif matched_phase:
            base.reason_codes = [code for code in base.reason_codes if code != "TARGET_PRESENT_IN_RECOVERY_SET"]
            _append_reason(base.reason_codes, "NO_RECOVERY_SET_MATCH")
        base.role_level = all(item.role_level for item in items)
        base.known_prereq = any(item.known_prereq for item in items)
        base.required_in_recovery_set = any(item.required_in_recovery_set for item in items)
        base.weak_heuristic = any(item.weak_heuristic for item in items)
        base.internal = any(item.internal for item in items)
        merged.append(base)
    return sorted(merged, key=lambda obs: (obs.category, obs.prerequisite_target or obs.prerequisite_name, obs.prerequisite_target_ip))


def _enrich_observation_from_match(observation: ObservedPrerequisite, match: RecoverySetMatch, recovery_set: RecoverySet) -> None:
    if not match.matched_systems:
        return
    matched_names = set(match.matched_systems)
    for system in recovery_set.systems:
        if system_display_name(system) not in matched_names:
            continue
        if not observation.prerequisite_target and system.fqdn:
            observation.prerequisite_target = system.fqdn
        if not observation.prerequisite_target_ip and system.ip_addresses:
            observation.prerequisite_target_ip = system.ip_addresses[0]
        observation.example_answer_names = _unique(observation.example_answer_names + [system.fqdn])
        observation.example_answer_ips = _unique(observation.example_answer_ips + system.ip_addresses)


def _best_match_basis(values: list[str]) -> str:
    order = {"IP_MATCH": 4, "HOSTNAME_MATCH": 3, "ALIAS_MATCH": 2, "ROLE_TAG_MATCH": 1, "NO_RECOVERY_SET_MATCH": 0, "": -1}
    return max(values or [""], key=lambda value: order.get(value, -1))


def _observation_dedupe_key(observation: ObservedPrerequisite) -> tuple[str, str]:
    if observation.role_level and not observation.prerequisite_target and not observation.prerequisite_target_ip and not observation.example_answer_ips:
        return (observation.category, "role-level")
    for ip in [observation.prerequisite_target_ip] + observation.example_answer_ips:
        if ip:
            return (observation.category, f"ip:{ip}")
    names = [observation.prerequisite_target] + observation.example_answer_names + observation.example_qnames
    for name in names:
        normalized = normalize_fqdn(name)
        if normalized:
            return (observation.category, f"name:{normalized}")
    return (observation.category, f"name:{normalize_fqdn(observation.prerequisite_name)}")


def _choose_observation_base(items: list[ObservedPrerequisite]) -> ObservedPrerequisite:
    def score(item: ObservedPrerequisite) -> tuple[int, int, int, int]:
        has_target_name = 1 if item.prerequisite_target else 0
        has_target_ip = 1 if item.prerequisite_target_ip else 0
        known = 1 if item.known_prereq else 0
        concrete_name = 1 if "." in item.prerequisite_name else 0
        return (known, has_target_name, has_target_ip, concrete_name)

    base = max(items, key=score)
    if not base.prerequisite_target:
        for item in items:
            if item.prerequisite_target:
                base = base.model_copy(update={"prerequisite_target": item.prerequisite_target})
                break
    if not base.prerequisite_target_ip:
        for item in items:
            if item.prerequisite_target_ip:
                base = base.model_copy(update={"prerequisite_target_ip": item.prerequisite_target_ip})
                break
    return base


def _max_confidence(values: list[str]) -> str:
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    return max(values or ["LOW"], key=lambda value: order.get(value, 0))


def _build_summary(
    findings: list[Finding],
    observed: list[ObservedPrerequisite],
    recovery_set: RecoverySet,
    warnings: list[str],
    assumptions: list[str],
    *,
    backup_rows: int,
    dns_rows: int,
    dns_rows_in_window: int,
    dns_rows_all: list[Any],
    dns_rows_window: list[Any],
    protected_systems: int,
    mapped_clients: int,
    unmapped_clients: int,
    resolver_identity_known: bool,
    config: dict[str, Any],
    answer_map_enriched: int = 0,
    accepted_risk_count: int = 0,
    recovery_set_metadata: dict[str, Any] | None = None,
    backup_inventory_rows_detail: list[Any] | None = None,
    input_paths: list[str | Path | None] | None = None,
    policy_pack: str | None = None,
) -> Summary:
    finding_counts = {"critical": 0, "warning": 0, "review": 0, "info": 0}
    for finding in findings:
        finding_counts[finding.severity.lower()] += 1
    category_counts = {category: 0 for category in sorted(SUPPORTED_CATEGORIES)}
    for observation in observed:
        category_counts[observation.category] = category_counts.get(observation.category, 0) + 1
    ordered_category_counts = {
        "dns_resolver": category_counts.get("dns_resolver", 0),
        "directory_service": category_counts.get("directory_service", 0),
        "kerberos_service": category_counts.get("kerberos_service", 0),
        "global_catalog": category_counts.get("global_catalog", 0),
        "vpn_endpoint": category_counts.get("vpn_endpoint", 0),
        "license_server": category_counts.get("license_server", 0),
        "database_host": category_counts.get("database_host", 0),
        "file_share": category_counts.get("file_share", 0),
        "time_service": category_counts.get("time_service", 0),
        "other_prerequisite": category_counts.get("other_prerequisite", 0),
    }
    if finding_counts["critical"]:
        status = "FAIL"
    elif finding_counts["warning"] or finding_counts["review"]:
        status = "REVIEW"
    elif config.get("require_resolver_identity_for_pass", True) and not resolver_identity_known:
        status = "REVIEW"
    elif mapped_clients == 0:
        status = "REVIEW"
    else:
        status = "PASS"
    top_missing = _unique([
        finding.prerequisite_name
        for finding in findings
        if not finding.present_in_recovery_set and finding.severity in {"CRITICAL", "WARNING", "REVIEW"}
    ])[:5]
    questions = _unique([finding.suggested_human_question for finding in findings if not finding.present_in_recovery_set and finding.severity != "INFO"])[:10]
    evidence_quality = _evidence_quality(
        dns_rows=dns_rows,
        dns_rows_in_window=dns_rows_in_window,
        dns_rows_all=dns_rows_all,
        dns_rows_window=dns_rows_window,
        backup_inventory_rows_detail=backup_inventory_rows_detail or [],
        mapped_clients=mapped_clients,
        unmapped_clients=unmapped_clients,
        resolver_identity_known=resolver_identity_known,
        answer_map_enriched=answer_map_enriched,
        warnings=warnings,
    )
    return Summary(
        schema_version="1.0",
        tool_version=__version__,
        lint_status=status,  # type: ignore[arg-type]
        recovery_set=recovery_set.name,
        input={
            "backup_inventory_rows": backup_rows,
            "dns_log_rows": dns_rows,
            "dns_log_rows_in_window": dns_rows_in_window,
            "protected_systems": protected_systems,
            "recovery_set_systems": len(recovery_set.systems),
            "mapped_dns_clients": mapped_clients,
            "unmapped_dns_clients": unmapped_clients,
        },
        evidence_quality=evidence_quality,
        findings=finding_counts,
        categories=ordered_category_counts,
        top_missing_prerequisites=top_missing,
        warnings=_unique(warnings),
        assumptions=_unique(assumptions),
        recommended_next_questions=questions,
        run_metadata={
            "input_fingerprints": _input_fingerprints(input_paths or []),
            "policy_pack": policy_pack or "",
            "config_window_hours": int(config.get("window_hours", 24)),
            "config_min_query_count": int(config.get("min_query_count", 2)),
            "accepted_risk_count": accepted_risk_count,
            "recovery_set_metadata": recovery_set_metadata or {},
            "business_context": _business_context(backup_inventory_rows_detail or [], recovery_set, findings),
        },
    )


def compare_windows(
    *,
    backup_inventory: str | Path,
    dns_log: str | Path,
    recovery_set_name: str | None,
    windows: list[int],
    known_prereqs_path: str | Path | None = None,
    resolver_hints_path: str | Path | None = None,
    answer_map_path: str | Path | None = None,
    accepted_risks_path: str | Path | None = None,
    recovery_sets_path: str | Path | None = None,
    config_path: str | Path | None = None,
    policy_pack: str | None = None,
    include_unmapped_clients: bool = False,
    include_external: bool | None = None,
    min_query_count: int | None = None,
) -> list[dict[str, Any]]:
    config = load_config(config_path, policy_pack=policy_pack)
    if min_query_count is not None:
        config["min_query_count"] = min_query_count
    if include_external is None:
        include_external = bool(config.get("include_external_by_default", False))

    warnings: list[str] = []
    assumptions: list[str] = []
    backup = _cached_parse_backup_inventory(backup_inventory, strict=False)
    recovery_set = build_recovery_set(backup.rows, recovery_set_name=recovery_set_name, strict=False)
    warnings.extend(backup.warnings)
    warnings.extend(recovery_set.warnings)
    dns = _cached_parse_dns_log(dns_log, strict=False)
    warnings.extend(dns.warnings)
    answer_entries = _cached_load_answer_map(answer_map_path)
    dns_rows, answer_map_enriched = enrich_dns_rows_with_answer_map(dns.rows, answer_entries)
    if answer_map_enriched:
        warnings.append("ANSWER_MAP_ENRICHED")
    known = _cached_load_known_prereqs(known_prereqs_path)
    if known.internal_domains:
        internal_domains = known.internal_domains
    else:
        internal_domains = infer_internal_domains(system.fqdn for system in backup.protected_systems if system.fqdn)
        warnings.append("INTERNAL_DOMAINS_INFERRED")
        assumptions.append("internal domains inferred from protected-system FQDNs" if internal_domains else "internal domains could not be declared or inferred")
    resolver_hints, resolver_warnings = _cached_load_resolver_hints(resolver_hints_path, strict=False)
    warnings.extend(resolver_warnings)
    accepted_risks = load_accepted_risks(accepted_risks_path)
    recovery_set_metadata = load_recovery_set_metadata(recovery_sets_path)
    selected_metadata = recovery_set_metadata.get(recovery_set.name)

    mapper = ClientMapper(backup.protected_systems)
    evidence_by_row: dict[int, list[QueryEvidence]] = {}
    row_identity: dict[int, tuple[str, bool]] = {}
    for row in dns_rows:
        mapped = mapper.map_query(row)
        identity = row.client_ip or row.client_name or f"dns:{row.source_row}"
        row_identity[row.source_row] = (identity, mapped.system is not None)
        if not mapped.system and not include_unmapped_clients:
            evidence_by_row[row.source_row] = []
            continue
        evidence_by_row[row.source_row] = classify_dns_query(
            row,
            mapped,
            known_prereqs=known,
            internal_domains=internal_domains,
            include_external=include_external,
        )

    comparison: list[dict[str, Any]] = []
    previous_missing: set[str] = set()
    for window in sorted(set(windows)):
        window_rows, window_warnings = filter_dns_window(dns_rows, window)
        row_ids = {row.source_row for row in window_rows}
        mapped_clients = {row_identity[row.source_row][0] for row in window_rows if row_identity.get(row.source_row, ("", False))[1]}
        unmapped_clients = {row_identity[row.source_row][0] for row in window_rows if not row_identity.get(row.source_row, ("", True))[1]}
        window_warnings_all = _unique(warnings + window_warnings + (["UNMAPPED_DNS_CLIENT"] if unmapped_clients else []))
        evidence = [item for row_id in row_ids for item in evidence_by_row.get(row_id, [])]
        resolver_evidence, resolver_identity_known = _resolver_evidence(resolver_hints, window_rows)
        evidence.extend(resolver_evidence)
        if not resolver_identity_known:
            window_warnings_all.append("DNS_RESOLVER_IDENTITY_UNKNOWN")
        observed, findings = _observed_and_findings_from_evidence(evidence, recovery_set, config, accepted_risks=accepted_risks)
        accepted_risk_count = sum(1 for item in observed if "ACCEPTED_RISK_APPLIED" in item.reason_codes)
        if accepted_risk_count:
            window_warnings_all.append("ACCEPTED_RISK_APPLIED")
        summary = _build_summary(
            findings,
            observed,
            recovery_set,
            window_warnings_all,
            assumptions,
            backup_rows=len(backup.rows),
            dns_rows=len(dns.rows),
            dns_rows_in_window=len(window_rows),
            dns_rows_all=dns_rows,
            dns_rows_window=window_rows,
            backup_inventory_rows_detail=backup.rows,
            protected_systems=len(backup.protected_systems),
            mapped_clients=len(mapped_clients),
            unmapped_clients=len(unmapped_clients),
            resolver_identity_known=resolver_identity_known,
            config=config,
            answer_map_enriched=answer_map_enriched,
            accepted_risk_count=accepted_risk_count,
            recovery_set_metadata=selected_metadata.model_dump() if selected_metadata else {},
            input_paths=[backup_inventory, dns_log, known_prereqs_path, resolver_hints_path, answer_map_path, accepted_risks_path, recovery_sets_path, config_path],
            policy_pack=policy_pack,
        )
        missing_now = set(summary.top_missing_prerequisites)
        comparison.append(
            {
                "window_hours": window,
                "lint_status": summary.lint_status,
                "dns_log_rows_in_window": summary.input.get("dns_log_rows_in_window", 0),
                "findings": summary.findings,
                "top_missing_prerequisites": summary.top_missing_prerequisites,
                "new_missing_prerequisites": sorted(missing_now - previous_missing),
                "persisting_missing_prerequisites": sorted(missing_now.intersection(previous_missing)),
                "no_longer_seen_missing_prerequisites": sorted(previous_missing - missing_now),
            }
        )
        previous_missing = missing_now
    return comparison


def _suggested_action(observation: ObservedPrerequisite) -> str:
    if observation.present_in_recovery_set:
        return "Confirm the observed prerequisite is intentionally included in the declared recovery set."
    return "Review whether this observed prerequisite candidate should be included in, restored before, or otherwise available to the declared recovery set."


def _suggested_question(category: str) -> str:
    questions = {
        "dns_resolver": "Which DNS resolvers will be available in the recovery network, and are they included in the recovery set?",
        "directory_service": "Which domain controllers should be started before application systems in the recovery test?",
        "kerberos_service": "Will Kerberos/KDC services be reachable from the isolated recovery network?",
        "global_catalog": "Does this workload require global catalog lookups during authentication or startup?",
        "database_host": "Is this database host restored as part of the same recovery set, or is it provided by another recovery process?",
        "file_share": "Is this file service restored as a VM, appliance, NAS, or separate storage service?",
        "license_server": "Will this license service be reachable during DR testing, and what happens if it is not?",
        "vpn_endpoint": "Is remote-access infrastructure required during this recovery scenario, or only for normal production access?",
        "time_service": "Which time source will the recovery network use, especially for authentication-sensitive systems?",
    }
    return questions.get(category, "Who owns this prerequisite candidate, and should it be available during the recovery test?")


def _append_reason(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _evidence_quality(
    *,
    dns_rows: int,
    dns_rows_in_window: int,
    dns_rows_all: list[Any],
    dns_rows_window: list[Any],
    backup_inventory_rows_detail: list[Any],
    mapped_clients: int,
    unmapped_clients: int,
    resolver_identity_known: bool,
    answer_map_enriched: int,
    warnings: list[str],
) -> dict[str, Any]:
    issues: list[str] = []
    rows_with_answer_names = sum(1 for row in dns_rows_window if getattr(row, "answer_names", []))
    rows_with_answer_ips = sum(1 for row in dns_rows_window if getattr(row, "answer_ips", []))
    input_audit = _input_audit(backup_inventory_rows_detail)
    qtypes = sorted({getattr(row, "qtype", "UNKNOWN") for row in dns_rows_window if getattr(row, "qtype", "")})
    rcodes = sorted({getattr(row, "rcode", "") for row in dns_rows_window if getattr(row, "rcode", "")})
    timestamped_rows = sum(1 for row in dns_rows_all if getattr(row, "timestamp", None) is not None)
    answer_name_pct = _pct(rows_with_answer_names, dns_rows_in_window)
    answer_ip_pct = _pct(rows_with_answer_ips, dns_rows_in_window)
    window_pct = _pct(dns_rows_in_window, dns_rows)
    mapped_pct = _pct(mapped_clients, mapped_clients + unmapped_clients)
    if dns_rows == 0:
        issues.append("DNS query log has no usable rows.")
    if dns_rows_in_window == 0 and dns_rows:
        issues.append("No DNS rows are inside the selected window.")
    if dns_rows and window_pct < 10:
        issues.append("Selected window contains less than 10 percent of parsed DNS rows.")
    if dns_rows_in_window and answer_ip_pct < 50:
        issues.append("Less than half of in-window DNS rows include answer IPs.")
    if dns_rows_in_window and len(qtypes) < 2:
        issues.append("DNS qtype diversity is low in the selected window.")
    if mapped_clients == 0:
        issues.append("No DNS clients mapped to protected systems.")
    if unmapped_clients:
        issues.append("Some DNS clients did not map to protected systems.")
    if not resolver_identity_known:
        issues.append("Resolver identity is unknown.")
    if "TIMESTAMP_UNPARSEABLE" in warnings:
        issues.append("One or more timestamps were missing or unparseable.")
    if answer_map_enriched:
        issues.append("Offline answer-map data enriched DNS rows with missing answer data.")
    if input_audit["stale_inventory_rows"]:
        issues.append("Backup inventory contains non-protected or stale rows.")
    if input_audit["duplicate_fqdn_count"]:
        issues.append("Backup inventory contains duplicate FQDN values.")
    if input_audit["duplicate_ip_count"]:
        issues.append("Backup inventory contains duplicate IP values.")
    if input_audit["conflicting_alias_count"]:
        issues.append("Backup inventory contains aliases assigned to more than one row.")
    status = "GOOD"
    if issues:
        status = "PARTIAL"
    if mapped_clients == 0 or not resolver_identity_known or dns_rows == 0:
        status = "WEAK"
    return {
        "status": status,
        "issues": issues,
        "answer_map_enriched_rows": answer_map_enriched,
        "metrics": {
            "answer_name_coverage_pct": answer_name_pct,
            "answer_ip_coverage_pct": answer_ip_pct,
            "window_coverage_pct": window_pct,
            "mapped_client_identity_pct": mapped_pct,
            "timestamp_parse_pct": _pct(timestamped_rows, dns_rows),
            "qtype_count": len(qtypes),
            "rcode_count": len(rcodes),
        },
        "input_audit": input_audit,
        "qtypes": qtypes,
        "rcodes": rcodes,
    }


def _pct(part: int, whole: int) -> float:
    if whole <= 0:
        return 0.0
    return round((part / whole) * 100, 2)


def _business_context(rows: list[Any], recovery_set: RecoverySet, findings: list[Finding]) -> dict[str, Any]:
    protected_rows = [row for row in rows if getattr(row, "protected", False)]
    recovery_names = {system_display_name(system) for system in recovery_set.systems}
    recovery_rows = [row for row in protected_rows if _row_display_name(row) in recovery_names]
    row_by_name: dict[str, Any] = {}
    for row in protected_rows:
        for name in _row_names(row):
            row_by_name.setdefault(name, row)
    impacted_rows: list[Any] = []
    for finding in findings:
        if finding.present_in_recovery_set or finding.severity == "INFO":
            continue
        for system_name in finding.example_protected_systems:
            row = row_by_name.get(normalize_fqdn(system_name)) or row_by_name.get(system_name.lower())
            if row is not None:
                impacted_rows.append(row)
    return {
        "protected_systems_by_owner_team": _count_raw_field(protected_rows, "owner_team"),
        "protected_systems_by_business_service": _count_raw_field(protected_rows, "business_service"),
        "protected_systems_by_criticality": _count_raw_field(protected_rows, "criticality"),
        "protected_systems_by_recovery_tier": _count_raw_field(protected_rows, "recovery_tier"),
        "protected_systems_by_site": _count_raw_field(protected_rows, "site"),
        "protected_systems_by_environment": _count_raw_field(protected_rows, "environment"),
        "recovery_set_systems_by_owner_team": _count_raw_field(recovery_rows, "owner_team"),
        "recovery_set_systems_by_business_service": _count_raw_field(recovery_rows, "business_service"),
        "recovery_set_systems_by_criticality": _count_raw_field(recovery_rows, "criticality"),
        "recovery_set_systems_by_recovery_tier": _count_raw_field(recovery_rows, "recovery_tier"),
        "recovery_set_systems_by_site": _count_raw_field(recovery_rows, "site"),
        "recovery_set_systems_by_environment": _count_raw_field(recovery_rows, "environment"),
        "impacted_examples_by_owner_team": _count_raw_field(impacted_rows, "owner_team"),
        "impacted_examples_by_business_service": _count_raw_field(impacted_rows, "business_service"),
        "impacted_examples_by_criticality": _count_raw_field(impacted_rows, "criticality"),
        "impacted_examples_by_recovery_tier": _count_raw_field(impacted_rows, "recovery_tier"),
        "impacted_examples_by_site": _count_raw_field(impacted_rows, "site"),
        "impacted_examples_by_environment": _count_raw_field(impacted_rows, "environment"),
    }


def _row_display_name(row: Any) -> str:
    return getattr(row, "fqdn", "") or getattr(row, "workload_name", "")


def _row_names(row: Any) -> list[str]:
    values = [
        getattr(row, "fqdn", ""),
        getattr(row, "workload_name", ""),
        getattr(row, "short_name", ""),
        *getattr(row, "aliases", []),
    ]
    return _unique([normalize_fqdn(value) or value.lower() for value in values if value])


def _count_raw_field(rows: list[Any], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        raw = getattr(row, "raw", {}) or {}
        value = str(raw.get(field) or "unknown").strip() or "unknown"
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _input_audit(rows: list[Any]) -> dict[str, Any]:
    fqdns: dict[str, int] = {}
    ips: dict[str, int] = {}
    aliases: dict[str, int] = {}
    stale_rows = 0
    missing_owner_team = 0
    missing_site = 0
    missing_environment = 0
    missing_business_service = 0
    missing_criticality = 0
    missing_recovery_tier = 0
    for row in rows:
        raw = getattr(row, "raw", {}) or {}
        if not getattr(row, "protected", False):
            stale_rows += 1
        fqdn = normalize_fqdn(getattr(row, "fqdn", ""))
        if fqdn:
            fqdns[fqdn] = fqdns.get(fqdn, 0) + 1
        for ip in getattr(row, "ip_addresses", []):
            ips[ip] = ips.get(ip, 0) + 1
        for alias in getattr(row, "aliases", []):
            normalized = normalize_fqdn(alias)
            if normalized:
                aliases[normalized] = aliases.get(normalized, 0) + 1
        if not raw.get("owner_team"):
            missing_owner_team += 1
        if not raw.get("site"):
            missing_site += 1
        if not raw.get("environment"):
            missing_environment += 1
        if not raw.get("business_service"):
            missing_business_service += 1
        if not raw.get("criticality"):
            missing_criticality += 1
        if not raw.get("recovery_tier"):
            missing_recovery_tier += 1
    duplicate_fqdns = {key: value for key, value in fqdns.items() if value > 1}
    duplicate_ips = {key: value for key, value in ips.items() if value > 1}
    conflicting_aliases = {key: value for key, value in aliases.items() if value > 1}
    return {
        "stale_inventory_rows": stale_rows,
        "duplicate_fqdn_count": len(duplicate_fqdns),
        "duplicate_ip_count": len(duplicate_ips),
        "conflicting_alias_count": len(conflicting_aliases),
        "missing_owner_team_rows": missing_owner_team,
        "missing_site_rows": missing_site,
        "missing_environment_rows": missing_environment,
        "missing_business_service_rows": missing_business_service,
        "missing_criticality_rows": missing_criticality,
        "missing_recovery_tier_rows": missing_recovery_tier,
        "duplicate_fqdn_examples": sorted(duplicate_fqdns)[:5],
        "duplicate_ip_examples": sorted(duplicate_ips)[:5],
        "conflicting_alias_examples": sorted(conflicting_aliases)[:5],
    }


def _input_fingerprints(paths: list[str | Path | None]) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    for path in paths:
        if path is None:
            continue
        file_path = Path(path)
        if not file_path.exists():
            continue
        fingerprints[str(file_path)] = _file_hash(file_path)
    return fingerprints


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cached_parse_backup_inventory(path: str | Path, *, strict: bool) -> Any:
    key = _file_cache_key(path)
    return _parse_backup_inventory_cached(key[0], strict, key[1], key[2])


def _cached_parse_dns_log(path: str | Path, *, strict: bool) -> Any:
    key = _file_cache_key(path)
    return _parse_dns_log_cached(key[0], strict, key[1], key[2])


def _cached_load_known_prereqs(path: str | Path | None) -> Any:
    if path is None:
        return load_known_prereqs(None)
    key = _file_cache_key(path)
    return _load_known_prereqs_cached(key[0], key[1], key[2])


def _cached_load_resolver_hints(path: str | Path | None, *, strict: bool) -> Any:
    if path is None:
        return load_resolver_hints(None, strict=strict)
    key = _file_cache_key(path)
    return _load_resolver_hints_cached(key[0], strict, key[1], key[2])


def _cached_load_answer_map(path: str | Path | None) -> Any:
    if path is None:
        return load_answer_map(None)
    key = _file_cache_key(path)
    return _load_answer_map_cached(key[0], key[1], key[2])


def _file_cache_key(path: str | Path) -> tuple[str, int, int]:
    file_path = Path(path).resolve()
    stat = file_path.stat()
    return str(file_path), stat.st_mtime_ns, stat.st_size


@lru_cache(maxsize=16)
def _parse_backup_inventory_cached(path: str, strict: bool, _mtime_ns: int, _size: int) -> Any:
    return parse_backup_inventory(path, strict=strict)


@lru_cache(maxsize=16)
def _parse_dns_log_cached(path: str, strict: bool, _mtime_ns: int, _size: int) -> Any:
    return parse_dns_log(path, strict=strict)


@lru_cache(maxsize=16)
def _load_known_prereqs_cached(path: str, _mtime_ns: int, _size: int) -> Any:
    return load_known_prereqs(path)


@lru_cache(maxsize=16)
def _load_resolver_hints_cached(path: str, strict: bool, _mtime_ns: int, _size: int) -> Any:
    return load_resolver_hints(path, strict=strict)


@lru_cache(maxsize=16)
def _load_answer_map_cached(path: str, _mtime_ns: int, _size: int) -> Any:
    return load_answer_map(path)
