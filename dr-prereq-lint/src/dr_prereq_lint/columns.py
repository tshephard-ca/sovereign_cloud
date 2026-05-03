"""Column alias definitions and CSV header resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


BACKUP_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "workload_name": ("workload_name", "name", "vm_name", "server_name", "hostname", "computer_name"),
    "fqdn": ("fqdn", "dns_name", "fully_qualified_domain_name"),
    "ip_addresses": ("ip_addresses", "ips", "ip", "primary_ip", "guest_ip"),
    "protected": ("protected", "is_protected", "backed_up", "in_backup"),
    "recovery_set": ("recovery_set", "recovery_group", "dr_set", "test_group"),
    "include_in_recovery_set": (
        "include_in_recovery_set",
        "included",
        "in_recovery_set",
        "recover",
        "selected_for_recovery",
    ),
    "aliases": ("aliases",),
    "role_tags": ("role_tags",),
    "os": ("os",),
    "backup_job": ("backup_job",),
    "last_success_utc": ("last_success_utc",),
    "application_owner": ("application_owner",),
    "owner_team": ("owner_team", "team", "support_team"),
    "environment": ("environment",),
    "business_service": ("business_service", "service", "application_service"),
    "criticality": ("criticality", "business_criticality"),
    "recovery_tier": ("recovery_tier", "rto_tier", "recovery_class"),
    "dependency_owner": ("dependency_owner", "service_owner"),
    "site": ("site",),
    "notes": ("notes",),
}


DNS_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp", "time", "event_time", "query_time"),
    "client_ip": ("client_ip", "src_ip", "source_ip", "requester_ip"),
    "client_name": ("client_name", "src_name", "source_name", "requester_name"),
    "qname": ("qname", "query_name", "name", "query"),
    "qtype": ("qtype", "query_type", "type"),
    "rcode": ("rcode", "response_code", "result"),
    "answer_names": ("answer_names", "answers", "answer_fqdns", "response_names", "targets"),
    "answer_ips": ("answer_ips", "response_ips", "ips"),
    "resolver_name": ("resolver_name", "dns_server", "server_name", "collector_name"),
    "resolver_ip": ("resolver_ip", "dns_server_ip", "server_ip"),
    "query_id": ("query_id",),
    "source_file": ("source_file",),
    "protocol": ("protocol",),
    "view": ("view",),
    "ttl": ("ttl",),
    "raw_line": ("raw_line",),
}


@dataclass(frozen=True)
class ColumnResolution:
    resolved: dict[str, str]
    missing: tuple[str, ...]


def canonical_header(header: str | None) -> str:
    return (header or "").strip().lower().replace(" ", "_").replace("-", "_")


def resolve_columns(headers: Iterable[str], aliases: dict[str, tuple[str, ...]]) -> ColumnResolution:
    by_canonical = {canonical_header(header): header for header in headers if header is not None}
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for field_name, field_aliases in aliases.items():
        match = next((alias for alias in field_aliases if canonical_header(alias) in by_canonical), None)
        if match is None:
            missing.append(field_name)
        else:
            resolved[field_name] = by_canonical[canonical_header(match)]
    return ColumnResolution(resolved=resolved, missing=tuple(missing))
