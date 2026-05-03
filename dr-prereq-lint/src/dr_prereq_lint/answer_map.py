"""Offline DNS answer-map import.

The answer map is an optional CSV that enriches normalized DNS query rows
when the DNS log lacks answer data. It never performs live DNS resolution.
"""

from __future__ import annotations

import csv
from pathlib import Path

from pydantic import BaseModel, Field

from .models import DnsQueryRow
from .normalize import normalize_fqdn, normalize_fqdn_list, normalize_ip_list


ANSWER_MAP_COLUMNS = ["qname", "qtype", "answer_names", "answer_ips", "source", "observed_utc"]


class AnswerMapEntry(BaseModel):
    source_row: int
    qname: str
    qtype: str = "UNKNOWN"
    answer_names: list[str] = Field(default_factory=list)
    answer_ips: list[str] = Field(default_factory=list)
    source: str = ""
    observed_utc: str = ""


def load_answer_map(path: str | Path | None) -> list[AnswerMapEntry]:
    if path is None:
        return []
    entries: list[AnswerMapEntry] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "qname" not in {field.lower() for field in reader.fieldnames}:
            raise ValueError("answer map must include qname")
        for row_num, row in enumerate(reader, start=2):
            qname = normalize_fqdn(row.get("qname"))
            if not qname:
                continue
            entries.append(
                AnswerMapEntry(
                    source_row=row_num,
                    qname=qname,
                    qtype=str(row.get("qtype") or "UNKNOWN").strip().upper() or "UNKNOWN",
                    answer_names=normalize_fqdn_list(row.get("answer_names"), whitespace=True),
                    answer_ips=normalize_ip_list(row.get("answer_ips")),
                    source=str(row.get("source") or "").strip(),
                    observed_utc=str(row.get("observed_utc") or "").strip(),
                )
            )
    return entries


def enrich_dns_rows_with_answer_map(rows: list[DnsQueryRow], entries: list[AnswerMapEntry]) -> tuple[list[DnsQueryRow], int]:
    if not entries:
        return rows, 0
    by_exact: dict[tuple[str, str], AnswerMapEntry] = {}
    by_name: dict[str, AnswerMapEntry] = {}
    for entry in entries:
        by_exact.setdefault((entry.qname, entry.qtype), entry)
        by_name.setdefault(entry.qname, entry)

    enriched: list[DnsQueryRow] = []
    count = 0
    for row in rows:
        entry = by_exact.get((row.qname, row.qtype)) or by_name.get(row.qname)
        if entry is None:
            enriched.append(row)
            continue
        changed = False
        updated = row.model_copy(deep=True)
        if not updated.answer_names and entry.answer_names:
            updated.answer_names = list(entry.answer_names)
            changed = True
        if not updated.answer_ips and entry.answer_ips:
            updated.answer_ips = list(entry.answer_ips)
            changed = True
        if changed:
            updated.raw["answer_map_source_row"] = entry.source_row
            updated.raw["answer_map_source"] = entry.source
            count += 1
        enriched.append(updated)
    return enriched, count
