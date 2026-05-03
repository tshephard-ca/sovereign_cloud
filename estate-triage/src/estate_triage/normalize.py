"""CSV normalization into internal models."""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path

from estate_triage.columns import BACKUP_ALIASES, INVENTORY_ALIASES, identify_columns
from estate_triage.models import BackupMetadata, TriageError, WorkloadInventory


BLANK_VALUES = {"", "na", "n/a", "none", "null", "-", "--"}


def normalize_name(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value.strip()).lower()


def clean_string(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if cleaned.lower() in BLANK_VALUES:
        return None
    return cleaned


def normalize_uuid(value: str | None) -> str | None:
    cleaned = clean_string(value)
    if cleaned is None:
        return None
    return re.sub(r"\s+", "", cleaned).lower()


def _field(row: dict[str, str], mapping: dict[str, str], canonical: str) -> str | None:
    header = mapping.get(canonical)
    if not header:
        return None
    return clean_string(row.get(header))


def _normalize_number_text(text: str) -> str:
    """Normalize deterministic thousands and decimal separators.

    CSV exports commonly mix plain numbers, thousands separators, and decimal
    commas. Ambiguous values such as ``1,024`` keep the existing MVP behavior
    and are treated as thousands-separated integers.
    """
    compact = re.sub(r"\s+", "", text.strip())
    if not compact:
        return compact
    if re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?", compact):
        return compact.replace(",", "")
    if re.fullmatch(r"[+-]?\d{1,3}(\.\d{3})+(,\d+)?", compact):
        return compact.replace(".", "").replace(",", ".")
    if re.fullmatch(r"[+-]?\d+,\d+", compact):
        integer, decimal = compact.rsplit(",", 1)
        if len(decimal) == 3 and len(integer) <= 3:
            return integer + decimal
        return integer + "." + decimal
    return compact.replace(",", "")


def parse_float(value: str | None, *, field: str, row_number: int, warnings: list[str]) -> float | None:
    cleaned = clean_string(value)
    if cleaned is None:
        return None
    text = cleaned.strip()
    if text.endswith("%"):
        text = text[:-1].strip()
    text = _normalize_number_text(text)
    try:
        return float(text)
    except ValueError:
        warnings.append(f"Row {row_number}: could not parse numeric field {field!r}: {cleaned!r}.")
        return None


def parse_int(value: str | None, *, field: str, row_number: int, warnings: list[str]) -> int | None:
    parsed = parse_float(value, field=field, row_number=row_number, warnings=warnings)
    if parsed is None:
        return None
    return int(parsed)


def parse_mib(value: str | None, *, field: str, row_number: int, warnings: list[str]) -> float | None:
    cleaned = clean_string(value)
    if cleaned is None:
        return None
    text = cleaned.strip().lower()
    match = re.fullmatch(r"([+-]?\d[\d,.\s]*)\s*([kmgt](?:i?b)?|b|mib|gib|tib)?", text)
    if not match:
        warnings.append(f"Row {row_number}: could not parse storage field {field!r}: {cleaned!r}.")
        return None

    number_text = _normalize_number_text(match.group(1))
    try:
        value_float = float(number_text)
    except ValueError:
        warnings.append(f"Row {row_number}: could not parse storage field {field!r}: {cleaned!r}.")
        return None
    unit = match.group(2) or "mib"
    multipliers = {
        "b": 1 / (1024 * 1024),
        "k": 1 / 1024,
        "kb": 1 / 1024,
        "kib": 1 / 1024,
        "m": 1,
        "mb": 1,
        "mib": 1,
        "g": 1024,
        "gb": 1024,
        "gib": 1024,
        "t": 1024 * 1024,
        "tb": 1024 * 1024,
        "tib": 1024 * 1024,
    }
    return value_float * multipliers[unit]


def parse_bool(value: str | None) -> bool | None:
    cleaned = clean_string(value)
    if cleaned is None:
        return None
    lowered = cleaned.lower()
    if lowered in {"true", "yes", "y", "1", "protected"}:
        return True
    if lowered in {"false", "no", "n", "0", "unprotected"}:
        return False
    return None


def parse_datetime(
    value: str | None,
    *,
    field: str,
    row_number: int,
    warnings: list[str],
) -> datetime | None:
    cleaned = clean_string(value)
    if cleaned is None:
        return None

    text = cleaned.strip()
    iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(iso_text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        pass

    slash = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
    if slash:
        first = int(slash.group(1))
        second = int(slash.group(2))
        year = int(slash.group(3))
        if first <= 12 and second <= 12:
            warnings.append(
                f"Row {row_number}: ambiguous date in {field!r}: {cleaned!r}; value ignored."
            )
            return None
        if first > 12 and second <= 12:
            day, month = first, second
        elif second > 12 and first <= 12:
            month, day = first, second
        else:
            warnings.append(f"Row {row_number}: invalid date in {field!r}: {cleaned!r}.")
            return None
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            warnings.append(f"Row {row_number}: invalid date in {field!r}: {cleaned!r}.")
            return None

    dotted = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text)
    if dotted:
        day = int(dotted.group(1))
        month = int(dotted.group(2))
        year = int(dotted.group(3))
        if day <= 12 and month <= 12:
            warnings.append(
                f"Row {row_number}: ambiguous date in {field!r}: {cleaned!r}; value ignored."
            )
            return None
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            warnings.append(f"Row {row_number}: invalid date in {field!r}: {cleaned!r}.")
            return None

    warnings.append(f"Row {row_number}: unsupported date format in {field!r}: {cleaned!r}.")
    return None


def _dict_reader(path: Path) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = reader.fieldnames or []
            rows = [(index, row) for index, row in enumerate(reader, start=2)]
    except OSError as exc:
        raise TriageError(f"Could not read CSV file {path}: {exc}") from exc
    return headers, rows


def read_inventory_csv(path: Path, *, strict: bool, warnings: list[str]) -> list[WorkloadInventory]:
    headers, rows = _dict_reader(path)
    if not headers:
        message = f"Inventory CSV {path} has no header row."
        if strict:
            raise TriageError(message)
        warnings.append(message)
        return []

    mapping = identify_columns(headers, INVENTORY_ALIASES)
    if "name" not in mapping:
        message = "Inventory CSV is missing a workload name column."
        if strict:
            raise TriageError(message)
        warnings.append(message)

    workloads: list[WorkloadInventory] = []
    for row_number, row in rows:
        name = _field(row, mapping, "name") or ""
        uuid = normalize_uuid(_field(row, mapping, "uuid"))
        if strict and not (name or uuid):
            raise TriageError(f"Inventory row {row_number} has neither workload name nor UUID.")
        if not (name or uuid):
            warnings.append(f"Inventory row {row_number} has neither workload name nor UUID; skipped.")
            continue

        workloads.append(
            WorkloadInventory(
                source_row=row_number,
                name=name,
                normalized_name=normalize_name(name),
                uuid=uuid,
                power_state=_field(row, mapping, "power_state"),
                cpu_count=parse_int(
                    _field(row, mapping, "cpu_count"),
                    field="cpu_count",
                    row_number=row_number,
                    warnings=warnings,
                ),
                memory_mib=parse_mib(
                    _field(row, mapping, "memory_mib"),
                    field="memory_mib",
                    row_number=row_number,
                    warnings=warnings,
                ),
                provisioned_mib=parse_mib(
                    _field(row, mapping, "provisioned_mib"),
                    field="provisioned_mib",
                    row_number=row_number,
                    warnings=warnings,
                ),
                in_use_mib=parse_mib(
                    _field(row, mapping, "in_use_mib"),
                    field="in_use_mib",
                    row_number=row_number,
                    warnings=warnings,
                ),
                os=_field(row, mapping, "os"),
                datacenter=_field(row, mapping, "datacenter"),
                cluster=_field(row, mapping, "cluster"),
                host=_field(row, mapping, "host"),
                snapshot_total_mib=parse_mib(
                    _field(row, mapping, "snapshot_total_mib"),
                    field="snapshot_total_mib",
                    row_number=row_number,
                    warnings=warnings,
                ),
                tools_status=_field(row, mapping, "tools_status"),
                cpu_usage_pct=parse_float(
                    _field(row, mapping, "cpu_usage_pct"),
                    field="cpu_usage_pct",
                    row_number=row_number,
                    warnings=warnings,
                ),
                memory_usage_pct=parse_float(
                    _field(row, mapping, "memory_usage_pct"),
                    field="memory_usage_pct",
                    row_number=row_number,
                    warnings=warnings,
                ),
                last_powered_on=parse_datetime(
                    _field(row, mapping, "last_powered_on"),
                    field="last_powered_on",
                    row_number=row_number,
                    warnings=warnings,
                ),
                last_seen=parse_datetime(
                    _field(row, mapping, "last_seen"),
                    field="last_seen",
                    row_number=row_number,
                    warnings=warnings,
                ),
                tags=_field(row, mapping, "tags"),
                notes=_field(row, mapping, "notes"),
            )
        )
    return workloads


def read_backup_csv(path: Path, *, strict: bool, warnings: list[str]) -> list[BackupMetadata]:
    headers, rows = _dict_reader(path)
    if not headers:
        message = f"Backup CSV {path} has no header row."
        if strict:
            raise TriageError(message)
        warnings.append(message)
        return []

    mapping = identify_columns(headers, BACKUP_ALIASES)
    if "name" not in mapping and "uuid" not in mapping:
        message = "Backup CSV is missing both workload name and UUID columns."
        if strict:
            raise TriageError(message)
        warnings.append(message)

    size_fields = ("backup_total_mib", "latest_full_mib", "total_backup_mib")
    if not any(field in mapping for field in size_fields):
        message = "Backup CSV is missing all backup size fields."
        if strict:
            raise TriageError(message)
        warnings.append(message)

    backups: list[BackupMetadata] = []
    for row_number, row in rows:
        name = _field(row, mapping, "name")
        uuid = normalize_uuid(_field(row, mapping, "uuid"))
        if strict and not (name or uuid):
            raise TriageError(f"Backup row {row_number} has neither workload name nor UUID.")
        if not (name or uuid):
            warnings.append(f"Backup row {row_number} has neither workload name nor UUID; skipped.")
            continue

        backup_total_mib = None
        for field in size_fields:
            backup_total_mib = parse_mib(
                _field(row, mapping, field),
                field=field,
                row_number=row_number,
                warnings=warnings,
            )
            if backup_total_mib is not None:
                break

        backups.append(
            BackupMetadata(
                source_row=row_number,
                name=name,
                normalized_name=normalize_name(name),
                uuid=uuid,
                backup_total_mib=backup_total_mib,
                latest_restore_point_utc=parse_datetime(
                    _field(row, mapping, "latest_restore_point_utc"),
                    field="latest_restore_point_utc",
                    row_number=row_number,
                    warnings=warnings,
                ),
                restore_point_count=parse_int(
                    _field(row, mapping, "restore_point_count"),
                    field="restore_point_count",
                    row_number=row_number,
                    warnings=warnings,
                ),
                avg_daily_change_mib=parse_mib(
                    _field(row, mapping, "avg_daily_change_mib"),
                    field="avg_daily_change_mib",
                    row_number=row_number,
                    warnings=warnings,
                ),
                latest_incremental_mib=parse_mib(
                    _field(row, mapping, "latest_incremental_mib"),
                    field="latest_incremental_mib",
                    row_number=row_number,
                    warnings=warnings,
                ),
                backup_job=_field(row, mapping, "backup_job"),
                backup_policy=_field(row, mapping, "backup_policy"),
                retention_days=parse_int(
                    _field(row, mapping, "retention_days"),
                    field="retention_days",
                    row_number=row_number,
                    warnings=warnings,
                ),
                immutable_until_utc=parse_datetime(
                    _field(row, mapping, "immutable_until_utc"),
                    field="immutable_until_utc",
                    row_number=row_number,
                    warnings=warnings,
                ),
                rpo_hours=parse_float(
                    _field(row, mapping, "rpo_hours"),
                    field="rpo_hours",
                    row_number=row_number,
                    warnings=warnings,
                ),
                rto_tier=_field(row, mapping, "rto_tier"),
                repository=_field(row, mapping, "repository"),
                protected=parse_bool(_field(row, mapping, "protected")),
                last_success_utc=parse_datetime(
                    _field(row, mapping, "last_success_utc"),
                    field="last_success_utc",
                    row_number=row_number,
                    warnings=warnings,
                ),
                last_failure_utc=parse_datetime(
                    _field(row, mapping, "last_failure_utc"),
                    field="last_failure_utc",
                    row_number=row_number,
                    warnings=warnings,
                ),
            )
        )
    return backups
