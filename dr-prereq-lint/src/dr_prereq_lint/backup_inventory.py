"""Backup inventory CSV parsing."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .columns import BACKUP_COLUMN_ALIASES, resolve_columns
from .models import BackupInventoryRow, ProtectedSystem
from .normalize import normalize_fqdn, normalize_fqdn_list, normalize_ip_list, parse_bool, short_name, split_multi


class BackupInventoryParseResult(BaseModel):
    rows: list[BackupInventoryRow] = Field(default_factory=list)
    protected_systems: list[ProtectedSystem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_columns: list[str] = Field(default_factory=list)


def parse_backup_inventory(path: str | Path, *, strict: bool = False) -> BackupInventoryParseResult:
    warnings: list[str] = []
    inventory_rows: list[BackupInventoryRow] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        resolution = resolve_columns(headers, BACKUP_COLUMN_ALIASES)
        if "workload_name" not in resolution.resolved:
            message = "backup inventory is missing a workload_name-like column"
            if strict:
                raise ValueError(message)
            warnings.append("MISSING_WORKLOAD_NAME_COLUMN")
            return BackupInventoryParseResult(warnings=warnings, missing_columns=["workload_name"])
        for row_num, raw_row in enumerate(reader, start=2):
            row = _parse_inventory_row(raw_row, resolution.resolved, row_num)
            if row.workload_name:
                inventory_rows.append(row)

    protected = [
        ProtectedSystem(
            source_row=row.source_row,
            workload_name=row.workload_name,
            fqdn=row.fqdn,
            short_name=row.short_name,
            ip_addresses=row.ip_addresses,
            recovery_set=row.recovery_set,
            include_in_recovery_set=row.include_in_recovery_set,
            aliases=row.aliases,
            role_tags=row.role_tags,
        )
        for row in inventory_rows
        if row.protected
    ]
    return BackupInventoryParseResult(
        rows=inventory_rows,
        protected_systems=protected,
        warnings=warnings,
        missing_columns=list(resolution.missing),
    )


def _value(raw_row: dict[str, Any], columns: dict[str, str], field_name: str) -> str:
    column = columns.get(field_name)
    return str(raw_row.get(column, "") if column else "").strip()


def _parse_inventory_row(raw_row: dict[str, Any], columns: dict[str, str], row_num: int) -> BackupInventoryRow:
    workload_name = _value(raw_row, columns, "workload_name")
    fqdn = normalize_fqdn(_value(raw_row, columns, "fqdn"))
    normalized_short = short_name(fqdn or workload_name)
    ip_addresses = normalize_ip_list(_value(raw_row, columns, "ip_addresses"))
    protected_value = parse_bool(_value(raw_row, columns, "protected"))
    include_value = parse_bool(_value(raw_row, columns, "include_in_recovery_set"))
    aliases = normalize_fqdn_list(_value(raw_row, columns, "aliases"))
    for alias in [workload_name, fqdn, normalized_short]:
        normalized_alias = normalize_fqdn(alias)
        if normalized_alias and normalized_alias not in aliases:
            aliases.append(normalized_alias)
    role_tags = [tag.strip().lower() for tag in split_multi(_value(raw_row, columns, "role_tags")) if tag.strip()]
    return BackupInventoryRow(
        source_row=row_num,
        workload_name=workload_name.strip(),
        fqdn=fqdn,
        short_name=normalized_short,
        ip_addresses=ip_addresses,
        protected=True if protected_value is None else protected_value,
        recovery_set=_value(raw_row, columns, "recovery_set"),
        include_in_recovery_set=include_value,
        aliases=aliases,
        role_tags=role_tags,
        raw=dict(raw_row),
    )
