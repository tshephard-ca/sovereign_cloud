"""Classify individual DNS query rows into prerequisite evidence."""

from __future__ import annotations

from itertools import zip_longest
import re

from .client_mapping import ClientMapResult, protected_system_key
from .known_prereqs import KnownPrereqSet
from .models import DnsQueryRow, QueryEvidence
from .normalize import is_private_or_internal_ip, qname_in_domains, short_name
from .recovery_set import system_display_name


VPN_PATTERNS = ("vpn", "sslvpn", "remote", "remoteaccess", "rdgateway", "gateway", "citr", "workspace", "portal")
LICENSE_PATTERNS = ("license", "licence", "lic", "flexlm", "lmgrd", "kms", "activation")
DATABASE_PATTERNS = ("sql", "mssql", "mysql", "postgres", "pgsql", "mongo", "oracle", "db", "database", "redis", "cassandra", "elastic", "opensearch")
FILE_PATTERNS = ("file", "files", "fs", "share", "shares", "dfs", "nas", "smb", "cifs", "nfs", "filer")
TIME_PATTERNS = ("ntp", "time", "timeserver")

DATABASE_SRV = ("_mssql._tcp", "_mysql._tcp", "_postgresql._tcp", "_mongodb._tcp")
FILE_SRV = ("_cifs._tcp", "_smb._tcp", "_nfs._tcp")


def classify_dns_query(
    query: DnsQueryRow,
    client_map: ClientMapResult,
    *,
    known_prereqs: KnownPrereqSet,
    internal_domains: list[str],
    include_external: bool = False,
) -> list[QueryEvidence]:
    if _is_reverse_ptr_noise(query) and not known_prereqs.matches(query.qname):
        return []

    mapped_system = client_map.system
    protected_name = system_display_name(mapped_system) if mapped_system else ""
    client_mapped = mapped_system is not None
    client_reason = "PROTECTED_CLIENT_MAPPED" if client_mapped else "UNMAPPED_DNS_CLIENT"
    internal = _is_internal_query(query, internal_domains)
    base_confidence = "HIGH" if client_map.match_basis in {"client_ip", "client_name_fqdn"} else "MEDIUM"
    if not client_mapped or client_map.match_basis in {"client_name_short", "client_name_alias"}:
        base_confidence = "LOW" if not client_mapped else "MEDIUM"

    evidence: list[QueryEvidence] = []
    known_matches = known_prereqs.matches(query.qname)
    for rule in known_matches:
        reason_codes = ["KNOWN_PREREQ_MATCH", client_reason]
        if query.answer_names:
            reason_codes.append("ANSWER_NAMES_PRESENT")
        if query.answer_ips:
            reason_codes.append("ANSWER_IPS_PRESENT")
        if not query.answer_names and not query.answer_ips:
            reason_codes.append("ANSWER_DATA_MISSING")
        if query.raw.get("answer_map_source_row"):
            reason_codes.append("ANSWER_MAP_ENRICHED")
        evidence.append(
            _evidence(
                query,
                category=rule.category,
                prerequisite_name=rule.display_name or rule.id,
                target=query.qname,
                target_ip="",
                confidence="HIGH" if client_mapped else "LOW",
                reason_codes=reason_codes,
                missing_data=_answer_missing(query),
                protected_name=protected_name,
                protected_key=protected_system_key(mapped_system),
                client_mapped=client_mapped,
                client_match_basis=client_map.match_basis,
                role_level=False,
                known_prereq=True,
                required=rule.required_in_recovery_set,
                internal=True,
            )
        )
    if known_matches:
        return evidence

    srv_evidence = _classify_directory_srv(query, protected_name, mapped_system, client_map, base_confidence)
    if srv_evidence:
        return srv_evidence

    service_evidence = _classify_service_srv(query, protected_name, mapped_system, client_map, base_confidence)
    if service_evidence:
        return service_evidence

    if query.qtype not in {"A", "AAAA", "CNAME", "UNKNOWN"}:
        return []

    if not internal and not include_external:
        return []

    heuristic = _classify_heuristic(query, internal=internal, include_external=include_external)
    if heuristic is None:
        return []
    category, confidence, weak = heuristic
    reason_codes = [client_reason, "HEURISTIC_ONLY_REVIEW"]
    if internal:
        reason_codes.append("INTERNAL_QNAME_HEURISTIC_MATCH")
    else:
        reason_codes.append("EXTERNAL_QNAME_INCLUDED")
    if not query.answer_names and not query.answer_ips:
        reason_codes.append("ANSWER_DATA_MISSING")
    if query.answer_names:
        reason_codes.append("ANSWER_NAMES_PRESENT")
    if query.answer_ips:
        reason_codes.append("ANSWER_IPS_PRESENT")
    if query.raw.get("answer_map_source_row"):
        reason_codes.append("ANSWER_MAP_ENRICHED")
    if not client_mapped:
        confidence = "LOW"
    elif base_confidence == "MEDIUM" and confidence == "HIGH":
        confidence = "MEDIUM"
    evidence.append(
        _evidence(
            query,
            category=category,
            prerequisite_name=query.qname,
            target=query.qname,
            target_ip="",
            confidence=confidence,
            reason_codes=reason_codes,
            missing_data=_answer_missing(query),
            protected_name=protected_name,
            protected_key=protected_system_key(mapped_system),
            client_mapped=client_mapped,
            client_match_basis=client_map.match_basis,
            role_level=False,
            known_prereq=False,
            required=True,
            internal=internal,
            weak_heuristic=weak,
        )
    )
    return evidence


def _classify_directory_srv(
    query: DnsQueryRow,
    protected_name: str,
    mapped_system: object,
    client_map: ClientMapResult,
    base_confidence: str,
) -> list[QueryEvidence]:
    if query.qtype != "SRV":
        return []
    qname = query.qname
    category = ""
    reason = ""
    prereq_name = ""
    if "_gc._tcp" in qname or "_ldap._tcp.gc._msdcs" in qname:
        category = "global_catalog"
        reason = "GLOBAL_CATALOG_LOOKUP_OBSERVED"
        prereq_name = "Global catalog lookup"
    elif "_kerberos._tcp" in qname or "_kerberos._udp" in qname or "_kpasswd._tcp" in qname or "_kpasswd._udp" in qname:
        category = "kerberos_service"
        reason = "KERBEROS_LOOKUP_OBSERVED"
        prereq_name = "Kerberos/KDC service lookup"
    elif "_ldap._tcp" in qname or "_msdcs" in qname:
        category = "directory_service"
        reason = "DIRECTORY_SERVICE_LOOKUP_OBSERVED"
        prereq_name = "Directory service lookup"
    if not category:
        return []
    extra_reasons = [reason, "SRV_LOOKUP_MATCH", "PROTECTED_CLIENT_MAPPED" if mapped_system else "UNMAPPED_DNS_CLIENT"]
    if "_ldap._tcp.pdc._msdcs" in qname:
        extra_reasons.append("PDC_EMULATOR_LOOKUP_OBSERVED")
    return _target_or_role_evidence(
        query,
        category=category,
        role_name=prereq_name,
        base_reason_codes=extra_reasons,
        confidence="HIGH" if mapped_system else "LOW",
        protected_name=protected_name,
        protected_key=protected_system_key(mapped_system),
        client_mapped=mapped_system is not None,
        client_match_basis=client_map.match_basis,
        internal=True,
    )


def _classify_service_srv(
    query: DnsQueryRow,
    protected_name: str,
    mapped_system: object,
    client_map: ClientMapResult,
    base_confidence: str,
) -> list[QueryEvidence]:
    if query.qtype != "SRV":
        return []
    category = ""
    role_name = ""
    if any(pattern in query.qname for pattern in DATABASE_SRV):
        category = "database_host"
        role_name = "Database service lookup"
    elif any(pattern in query.qname for pattern in FILE_SRV):
        category = "file_share"
        role_name = "File service lookup"
    if not category:
        return []
    return _target_or_role_evidence(
        query,
        category=category,
        role_name=role_name,
        base_reason_codes=["SRV_LOOKUP_MATCH", "PROTECTED_CLIENT_MAPPED" if mapped_system else "UNMAPPED_DNS_CLIENT"],
        confidence="HIGH" if mapped_system else "LOW",
        protected_name=protected_name,
        protected_key=protected_system_key(mapped_system),
        client_mapped=mapped_system is not None,
        client_match_basis=client_map.match_basis,
        internal=True,
    )


def _target_or_role_evidence(
    query: DnsQueryRow,
    *,
    category: str,
    role_name: str,
    base_reason_codes: list[str],
    confidence: str,
    protected_name: str,
    protected_key: str,
    client_mapped: bool,
    client_match_basis: str,
    internal: bool,
) -> list[QueryEvidence]:
    reason_codes = list(base_reason_codes)
    if query.answer_names:
        reason_codes.append("ANSWER_NAMES_PRESENT")
    if query.answer_ips:
        reason_codes.append("ANSWER_IPS_PRESENT")
    if query.raw.get("answer_map_source_row"):
        reason_codes.append("ANSWER_MAP_ENRICHED")
    evidence: list[QueryEvidence] = []
    if query.answer_names or query.answer_ips:
        for target, target_ip in zip_longest(query.answer_names, query.answer_ips, fillvalue=""):
            display = target or target_ip or role_name
            evidence.append(
                _evidence(
                    query,
                    category=category,
                    prerequisite_name=display,
                    target=target,
                    target_ip=target_ip,
                    confidence=confidence,
                    reason_codes=reason_codes,
                    missing_data=[],
                    protected_name=protected_name,
                    protected_key=protected_key,
                    client_mapped=client_mapped,
                    client_match_basis=client_match_basis,
                    role_level=False,
                    internal=internal,
                )
            )
    else:
        evidence.append(
            _evidence(
                query,
                category=category,
                prerequisite_name=role_name,
                target="",
                target_ip="",
                confidence="MEDIUM" if confidence == "HIGH" else "LOW",
                reason_codes=reason_codes + ["ANSWER_DATA_MISSING"],
                missing_data=["answer_names", "answer_ips"],
                protected_name=protected_name,
                protected_key=protected_key,
                client_mapped=client_mapped,
                client_match_basis=client_match_basis,
                role_level=True,
                internal=internal,
            )
        )
    return evidence


def _classify_heuristic(query: DnsQueryRow, *, internal: bool, include_external: bool) -> tuple[str, str, bool] | None:
    labels = [label for label in re.split(r"[._-]+", query.qname.lower()) if label]
    first = labels[0] if labels else short_name(query.qname)
    if _matches(labels, first, VPN_PATTERNS):
        return "vpn_endpoint", "MEDIUM" if internal else "LOW", False
    if _matches(labels, first, LICENSE_PATTERNS):
        weak = first in {"lic"} or first.startswith("lic")
        return "license_server", "LOW" if weak else "MEDIUM", weak
    if _matches(labels, first, DATABASE_PATTERNS):
        weak = first in {"db"} or first.startswith("db")
        return "database_host", "LOW" if weak else "MEDIUM", weak
    if _matches(labels, first, FILE_PATTERNS):
        weak = first in {"fs", "share", "shares"} or first.startswith("fs")
        return "file_share", "LOW" if weak else "MEDIUM", weak
    if _matches(labels, first, TIME_PATTERNS):
        return "time_service", "LOW" if not internal and include_external else "MEDIUM", True
    return None


def _matches(labels: list[str], first: str, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if pattern in labels or first.startswith(pattern):
            return True
    return False


def _is_internal_query(query: DnsQueryRow, internal_domains: list[str]) -> bool:
    return qname_in_domains(query.qname, internal_domains) or any(is_private_or_internal_ip(ip) for ip in query.answer_ips)


def _is_reverse_ptr_noise(query: DnsQueryRow) -> bool:
    return query.qtype == "PTR" and (query.qname.endswith(".in-addr.arpa") or query.qname.endswith(".ip6.arpa"))


def _answer_missing(query: DnsQueryRow) -> list[str]:
    missing: list[str] = []
    if not query.answer_names:
        missing.append("answer_names")
    if not query.answer_ips:
        missing.append("answer_ips")
    return missing


def _evidence(
    query: DnsQueryRow,
    *,
    category: str,
    prerequisite_name: str,
    target: str,
    target_ip: str,
    confidence: str,
    reason_codes: list[str],
    missing_data: list[str],
    protected_name: str,
    protected_key: str,
    client_mapped: bool,
    client_match_basis: str,
    role_level: bool,
    known_prereq: bool = False,
    required: bool = True,
    internal: bool = False,
    weak_heuristic: bool = False,
) -> QueryEvidence:
    return QueryEvidence(
        category=category,
        prerequisite_name=prerequisite_name,
        prerequisite_target=target,
        prerequisite_target_ip=target_ip,
        confidence=confidence,  # type: ignore[arg-type]
        evidence_source="dns_query_log",
        reason_codes=_unique(reason_codes),
        missing_data=_unique(missing_data),
        source_rows=[f"dns:{query.source_row}"],
        protected_system=protected_name,
        protected_system_key=protected_key,
        client_mapped=client_mapped,
        client_match_basis=client_match_basis,
        qname=query.qname,
        answer_names=query.answer_names,
        answer_ips=query.answer_ips,
        role_level=role_level,
        known_prereq=known_prereq,
        required_in_recovery_set=required,
        internal=internal,
        weak_heuristic=weak_heuristic,
    )


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
