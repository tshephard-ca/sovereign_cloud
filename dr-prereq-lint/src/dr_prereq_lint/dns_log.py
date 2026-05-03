"""Normalized DNS query CSV parsing and window filtering."""

from __future__ import annotations

import csv
from datetime import timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .columns import DNS_COLUMN_ALIASES, resolve_columns
from .models import DnsQueryRow
from .normalize import clean_text, normalize_fqdn, normalize_fqdn_list, normalize_ip, normalize_ip_list, parse_timestamp


class DnsLogParseResult(BaseModel):
    rows: list[DnsQueryRow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_columns: list[str] = Field(default_factory=list)


def parse_dns_log(path: str | Path, *, strict: bool = False) -> DnsLogParseResult:
    warnings: list[str] = []
    rows: list[DnsQueryRow] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        resolution = resolve_columns(headers, DNS_COLUMN_ALIASES)
        if "qname" not in resolution.resolved:
            message = "DNS query log is missing a qname-like column"
            if strict:
                raise ValueError(message)
            warnings.append("MISSING_QNAME_COLUMN")
            return DnsLogParseResult(warnings=warnings, missing_columns=["qname"])
        if "client_ip" not in resolution.resolved and "client_name" not in resolution.resolved:
            message = "DNS query log is missing both client_ip-like and client_name-like columns"
            if strict:
                raise ValueError(message)
            warnings.append("MISSING_DNS_CLIENT_COLUMN")
        if "qtype" not in resolution.resolved and strict:
            raise ValueError("DNS query log is missing a qtype-like column")
        for row_num, raw_row in enumerate(reader, start=2):
            row = _parse_dns_row(raw_row, resolution.resolved, row_num)
            if row is None:
                continue
            rows.append(row)
            if row.timestamp_raw and row.timestamp is None and "TIMESTAMP_UNPARSEABLE" not in warnings:
                warnings.append("TIMESTAMP_UNPARSEABLE")
            if not row.timestamp_raw and "TIMESTAMP_UNPARSEABLE" not in warnings:
                warnings.append("TIMESTAMP_UNPARSEABLE")
    return DnsLogParseResult(rows=rows, warnings=warnings, missing_columns=list(resolution.missing))


def filter_dns_window(rows: list[DnsQueryRow], window_hours: int | None) -> tuple[list[DnsQueryRow], list[str]]:
    if not rows or not window_hours:
        return rows, []
    if any(row.timestamp is None for row in rows):
        return rows, ["TIMESTAMP_UNPARSEABLE", "DNS_LOG_WINDOW_ASSUMED"]
    window_end = max(row.timestamp for row in rows if row.timestamp is not None)
    window_start = window_end - timedelta(hours=window_hours)
    return [row for row in rows if row.timestamp and row.timestamp >= window_start], []


def _value(raw_row: dict[str, Any], columns: dict[str, str], field_name: str) -> str:
    column = columns.get(field_name)
    return str(raw_row.get(column, "") if column else "").strip()


def _parse_dns_row(raw_row: dict[str, Any], columns: dict[str, str], row_num: int) -> DnsQueryRow | None:
    qname = normalize_fqdn(_value(raw_row, columns, "qname"))
    if not qname:
        return None
    timestamp_raw = _value(raw_row, columns, "timestamp")
    client_name = normalize_fqdn(_value(raw_row, columns, "client_name"))
    qtype = clean_text(_value(raw_row, columns, "qtype")).upper() or "UNKNOWN"
    return DnsQueryRow(
        source_row=row_num,
        timestamp=parse_timestamp(timestamp_raw),
        timestamp_raw=timestamp_raw,
        client_ip=normalize_ip(_value(raw_row, columns, "client_ip")),
        client_name=client_name,
        qname=qname,
        qtype=qtype,
        rcode=clean_text(_value(raw_row, columns, "rcode")).upper(),
        answer_names=normalize_fqdn_list(_value(raw_row, columns, "answer_names"), whitespace=True),
        answer_ips=normalize_ip_list(_value(raw_row, columns, "answer_ips")),
        resolver_name=normalize_fqdn(_value(raw_row, columns, "resolver_name")),
        resolver_ip=normalize_ip(_value(raw_row, columns, "resolver_ip")),
        raw=dict(raw_row),
    )
