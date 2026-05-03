"""Input validation explain reports."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .backup_inventory import parse_backup_inventory
from .columns import BACKUP_COLUMN_ALIASES, DNS_COLUMN_ALIASES, resolve_columns
from .config import load_config
from .known_prereqs import load_known_prereqs
from .normalize import parse_timestamp
from .resolver_hints import load_resolver_hints


def build_validation_report(
    *,
    backup_inventory: str | Path,
    dns_log: str | Path,
    known_prereqs: str | Path | None = None,
    resolver_hints: str | Path | None = None,
    config: str | Path | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    backup_headers = _headers(backup_inventory)
    dns_headers = _headers(dns_log)
    backup_columns = resolve_columns(backup_headers, BACKUP_COLUMN_ALIASES)
    dns_columns = resolve_columns(dns_headers, DNS_COLUMN_ALIASES)
    backup = parse_backup_inventory(backup_inventory, strict=strict)
    dns_fast = _inspect_dns_fast(dns_log, dns_columns.resolved, dns_columns.missing, strict=strict)
    known_count = 0
    resolver_count = 0
    if known_prereqs:
        known = load_known_prereqs(known_prereqs)
        known_count = len(known.prerequisites)
    if resolver_hints:
        resolvers, _ = load_resolver_hints(resolver_hints, strict=strict)
        resolver_count = len(resolvers)
    load_config(config)
    return {
        "schema_version": "1.0",
        "valid": True,
        "backup_inventory": {
            "path": str(backup_inventory),
            "rows": len(backup.rows),
            "protected_systems": len(backup.protected_systems),
            "headers": backup_headers,
            "mapped_columns": backup_columns.resolved,
            "missing_columns": list(backup_columns.missing),
            "warnings": backup.warnings,
        },
        "dns_log": {
            "path": str(dns_log),
            "rows": dns_fast["rows"],
            "headers": dns_headers,
            "mapped_columns": dns_columns.resolved,
            "missing_columns": list(dns_columns.missing),
            "warnings": dns_fast["warnings"],
            "rows_with_answer_names": dns_fast["rows_with_answer_names"],
            "rows_with_answer_ips": dns_fast["rows_with_answer_ips"],
            "rows_with_resolver_identity": dns_fast["rows_with_resolver_identity"],
            "sampled_rows_for_timestamp_parse": dns_fast["sampled_rows_for_timestamp_parse"],
            "sampled_unparseable_timestamps": dns_fast["sampled_unparseable_timestamps"],
        },
        "known_prereqs": {"path": str(known_prereqs or ""), "rules": known_count},
        "resolver_hints": {"path": str(resolver_hints or ""), "resolvers": resolver_count},
    }


def _headers(path: str | Path) -> list[str]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        return next(reader, [])


def _inspect_dns_fast(path: str | Path, columns: dict[str, str], missing_columns: list[str] | tuple[str, ...], *, strict: bool) -> dict[str, Any]:
    warnings: list[str] = []
    if "qname" not in columns:
        message = "DNS query log is missing a qname-like column"
        if strict:
            raise ValueError(message)
        warnings.append("MISSING_QNAME_COLUMN")
    if "client_ip" not in columns and "client_name" not in columns:
        message = "DNS query log is missing both client_ip-like and client_name-like columns"
        if strict:
            raise ValueError(message)
        warnings.append("MISSING_DNS_CLIENT_COLUMN")
    rows = 0
    answer_names = 0
    answer_ips = 0
    resolver_identity = 0
    sampled_ts = 0
    bad_ts = 0
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows += 1
            if columns.get("answer_names") and str(row.get(columns["answer_names"], "")).strip():
                answer_names += 1
            if columns.get("answer_ips") and str(row.get(columns["answer_ips"], "")).strip():
                answer_ips += 1
            has_resolver_name = columns.get("resolver_name") and str(row.get(columns["resolver_name"], "")).strip()
            has_resolver_ip = columns.get("resolver_ip") and str(row.get(columns["resolver_ip"], "")).strip()
            if has_resolver_name or has_resolver_ip:
                resolver_identity += 1
            if sampled_ts < 1000 and columns.get("timestamp"):
                sampled_ts += 1
                raw_ts = str(row.get(columns["timestamp"], "")).strip()
                if not raw_ts or parse_timestamp(raw_ts) is None:
                    bad_ts += 1
    if bad_ts and "TIMESTAMP_UNPARSEABLE" not in warnings:
        warnings.append("TIMESTAMP_UNPARSEABLE")
    return {
        "rows": rows,
        "warnings": warnings,
        "rows_with_answer_names": answer_names,
        "rows_with_answer_ips": answer_ips,
        "rows_with_resolver_identity": resolver_identity,
        "sampled_rows_for_timestamp_parse": sampled_ts,
        "sampled_unparseable_timestamps": bad_ts,
    }
