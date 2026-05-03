from __future__ import annotations

import csv
from pathlib import Path

import pytest


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str] | None = None) -> Path:
    fieldnames = fieldnames or list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_text(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def csv_writer():
    return write_csv


@pytest.fixture
def text_writer():
    return write_text


def inventory_rows(*, include_dc: bool = False, include_dns: bool = False, include_flag: bool = True) -> list[dict[str, str]]:
    include_col = "true" if include_flag else ""
    rows = [
        {
            "workload_name": "app01",
            "fqdn": "app01.apps.example.internal",
            "ip_addresses": "10.0.1.10",
            "protected": "true",
            "recovery_set": "dr-test-001",
            "include_in_recovery_set": include_col,
            "aliases": "app01-short",
            "role_tags": "application",
        }
    ]
    rows.append(
        {
            "workload_name": "dc01",
            "fqdn": "dc01.corp.example.internal",
            "ip_addresses": "10.0.0.20",
            "protected": "true",
            "recovery_set": "dr-test-001" if include_dc else "core-services",
            "include_in_recovery_set": include_col if include_dc else "false",
            "aliases": "",
            "role_tags": "domain_controller;kerberos;global_catalog",
        }
    )
    rows.append(
        {
            "workload_name": "dns01",
            "fqdn": "dns01.example.internal",
            "ip_addresses": "10.0.0.10",
            "protected": "true",
            "recovery_set": "dr-test-001" if include_dns else "core-services",
            "include_in_recovery_set": include_col if include_dns else "false",
            "aliases": "",
            "role_tags": "dns_resolver",
        }
    )
    return rows


def dns_rows(qname: str = "sql01.apps.example.internal", *, client_ip: str = "10.0.1.10", qtype: str = "A") -> list[dict[str, str]]:
    return [
        {
            "timestamp": "2026-04-29T08:00:00Z",
            "client_ip": client_ip,
            "client_name": "app01.apps.example.internal",
            "qname": qname,
            "qtype": qtype,
            "rcode": "NOERROR",
            "answer_names": "",
            "answer_ips": "10.0.2.30",
            "resolver_name": "dns01.example.internal",
            "resolver_ip": "10.0.0.10",
        }
    ]
