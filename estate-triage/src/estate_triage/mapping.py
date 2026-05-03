"""Column mapping specifications for arbitrary CSV exports."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from estate_triage.columns import (
    BACKUP_ALIASES,
    INVENTORY_ALIASES,
    UTILIZATION_ALIASES,
    identify_columns,
)
from estate_triage.models import TriageError


MappingKind = Literal["inventory", "backup", "utilization"]
MAPPING_SCHEMA_VERSION = "1.0.0"


class ColumnMapping(BaseModel):
    source_kind: MappingKind
    schema_version: str = MAPPING_SCHEMA_VERSION
    columns: dict[str, str] = Field(default_factory=dict)
    units: dict[str, str] = Field(default_factory=dict)
    approved_by: str | None = None
    approved_at_utc: str | None = None
    approval_notes: str | None = None
    notes: str | None = None


ALIASES_BY_KIND = {
    "inventory": INVENTORY_ALIASES,
    "backup": BACKUP_ALIASES,
    "utilization": UTILIZATION_ALIASES,
}


def load_column_mapping(path: Path | None, *, kind: MappingKind) -> ColumnMapping | None:
    if path is None:
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise TriageError(f"Could not read mapping file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise TriageError(f"Could not parse mapping YAML {path}: {exc}") from exc
    try:
        mapping = ColumnMapping(**raw)
    except Exception as exc:
        raise TriageError(f"Invalid mapping file {path}: {exc}") from exc
    if mapping.source_kind != kind:
        raise TriageError(
            f"Mapping file {path} is for {mapping.source_kind}, but {kind} was requested."
        )
    return mapping


def headers_for(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            return reader.fieldnames or []
    except UnicodeDecodeError as exc:
        raise TriageError(f"CSV file {path} is not valid UTF-8: {exc}") from exc
    except csv.Error as exc:
        raise TriageError(f"Could not parse CSV file {path}: {exc}") from exc
    except OSError as exc:
        raise TriageError(f"Could not read CSV file {path}: {exc}") from exc


def inferred_mapping(kind: MappingKind, headers: list[str]) -> ColumnMapping:
    return ColumnMapping(
        source_kind=kind,
        columns=identify_columns(headers, ALIASES_BY_KIND[kind]),
    )


def write_initial_mapping(*, kind: MappingKind, input_path: Path, output_path: Path) -> ColumnMapping:
    mapping = inferred_mapping(kind, headers_for(input_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(mapping.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return mapping


def effective_mapping(
    *,
    kind: MappingKind,
    headers: list[str],
    mapping: ColumnMapping | None,
) -> dict[str, str]:
    if mapping is None:
        return inferred_mapping(kind, headers).columns
    valid_headers = set(headers)
    missing = [
        header
        for header in mapping.columns.values()
        if header not in valid_headers
    ]
    if missing:
        raise TriageError(
            "Mapping references columns not present in input: " + ", ".join(sorted(missing))
        )
    return dict(mapping.columns)
