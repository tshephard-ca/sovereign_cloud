"""CSV adapters that emit canonical evidence and provenance."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from estate_triage.columns import (
    BACKUP_ALIASES,
    INVENTORY_ALIASES,
    UTILIZATION_ALIASES,
    column_key,
    identify_columns,
)
from estate_triage.evidence import (
    AdapterResult,
    DataQualityFinding,
    EvidenceField,
    EvidenceRecord,
    EvidenceSet,
    SourceRef,
)
from estate_triage.models import BackupMetadata, TriageError, WorkloadInventory
from estate_triage.mapping import ColumnMapping, effective_mapping
from estate_triage.normalize import (
    clean_string,
    normalize_name,
    normalize_uuid,
    parse_bool,
    parse_datetime,
    parse_float,
    parse_int,
    parse_mib,
)


def _dict_reader(path: Path) -> tuple[list[str], list[tuple[int, dict[str, str]]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            headers = reader.fieldnames or []
            rows = []
            for index, row in enumerate(reader, start=2):
                rows.append((index, row))
    except UnicodeDecodeError as exc:
        raise TriageError(f"CSV file {path} is not valid UTF-8: {exc}") from exc
    except csv.Error as exc:
        raise TriageError(f"Could not parse CSV file {path}: {exc}") from exc
    except OSError as exc:
        raise TriageError(f"Could not read CSV file {path}: {exc}") from exc
    return headers, rows


def _raw(row: dict[str, str], mapping: dict[str, str], canonical: str) -> str | None:
    header = mapping.get(canonical)
    if header is None:
        return None
    return row.get(header)


def _source_ref(path: Path, source_type: str, row_number: int, column_name: str | None = None) -> SourceRef:
    return SourceRef(
        source_type=source_type,  # type: ignore[arg-type]
        path=str(path),
        row_number=row_number,
        column_name=column_name,
    )


def _record_ref(path: Path, source_type: str, row_number: int) -> SourceRef:
    return _source_ref(path, source_type, row_number)


def _header_quality(
    *,
    headers: list[str],
    path: Path,
    source_type: str,
    strict: bool,
    warnings: list[str],
    data_quality: list[DataQualityFinding],
) -> None:
    seen: dict[str, str] = {}
    for header in headers:
        key = column_key(header)
        if not key:
            message = f"{source_type.title()} CSV has a blank header column."
            if strict:
                raise TriageError(message)
            warnings.append(message)
            data_quality.append(
                DataQualityFinding(
                    code="BLANK_HEADER",
                    severity="warning",
                    message=message,
                    field=header,
                    source_refs=[_source_ref(path, source_type, 1, header)],
                )
            )
            continue
        if key in seen:
            previous = seen[key]
            message = (
                f"{source_type.title()} CSV has duplicate header columns "
                f"{previous!r} and {header!r}."
            )
            if strict:
                raise TriageError(message)
            warnings.append(message)
            data_quality.append(
                DataQualityFinding(
                    code="DUPLICATE_HEADER",
                    severity="warning",
                    message=message,
                    field=header,
                    source_refs=[
                        _source_ref(path, source_type, 1, previous),
                        _source_ref(path, source_type, 1, header),
                    ],
                )
            )
        else:
            seen[key] = header


def _row_shape_quality(
    *,
    row: dict[str, Any],
    path: Path,
    source_type: str,
    row_number: int,
) -> list[DataQualityFinding]:
    findings: list[DataQualityFinding] = []
    extra_values = row.get(None)
    if extra_values:
        findings.append(
            DataQualityFinding(
                code="EXTRA_CSV_COLUMNS",
                severity="warning",
                message=(
                    f"{source_type.title()} row {row_number} has more values than header columns; "
                    "extra values were ignored."
                ),
                source_refs=[_record_ref(path, source_type, row_number)],
            )
        )
    missing_columns = [
        header
        for header, value in row.items()
        if header is not None and value is None
    ]
    if missing_columns:
        findings.append(
            DataQualityFinding(
                code="MISSING_CSV_COLUMNS",
                severity="warning",
                message=(
                    f"{source_type.title()} row {row_number} has fewer values than header columns."
                ),
                source_refs=[
                    _source_ref(path, source_type, row_number, column_name)
                    for column_name in missing_columns
                ],
            )
        )
    return findings


def _numeric_range_quality(
    *,
    fields: dict[str, EvidenceField],
    source_type: str,
    row_number: int,
) -> list[DataQualityFinding]:
    findings: list[DataQualityFinding] = []

    def value(name: str) -> Any:
        field = fields.get(name)
        return None if field is None else field.value

    def ref(name: str) -> SourceRef:
        field = fields[name]
        return field.source_ref

    non_negative_fields = (
        "cpu_count",
        "memory_mib",
        "provisioned_mib",
        "in_use_mib",
        "snapshot_total_mib",
        "backup_total_mib",
        "latest_full_mib",
        "total_backup_mib",
        "restore_point_count",
        "avg_daily_change_mib",
        "latest_incremental_mib",
        "retention_days",
        "rpo_hours",
        "sample_count",
    )
    for field_name in non_negative_fields:
        parsed = value(field_name)
        if isinstance(parsed, (int, float)) and parsed < 0:
            findings.append(
                DataQualityFinding(
                    code="NEGATIVE_VALUE",
                    severity="warning",
                    message=f"{source_type.title()} row {row_number} has a negative {field_name} value.",
                    field=field_name,
                    source_refs=[ref(field_name)],
                )
            )

    percent_fields = (
        "cpu_usage_pct",
        "memory_usage_pct",
        "cpu_avg_pct",
        "cpu_p95_pct",
        "cpu_max_pct",
        "memory_avg_pct",
        "memory_p95_pct",
        "memory_max_pct",
    )
    for field_name in percent_fields:
        parsed = value(field_name)
        if isinstance(parsed, (int, float)) and (parsed < 0 or parsed > 100):
            findings.append(
                DataQualityFinding(
                    code="PERCENT_OUT_OF_RANGE",
                    severity="warning",
                    message=f"{source_type.title()} row {row_number} has {field_name} outside 0-100.",
                    field=field_name,
                    source_refs=[ref(field_name)],
                )
            )

    provisioned = value("provisioned_mib")
    in_use = value("in_use_mib")
    if (
        isinstance(provisioned, (int, float))
        and isinstance(in_use, (int, float))
        and provisioned >= 0
        and in_use > provisioned
    ):
        findings.append(
            DataQualityFinding(
                code="IN_USE_EXCEEDS_PROVISIONED",
                severity="warning",
                message=(
                    f"{source_type.title()} row {row_number} has in-use storage greater "
                    "than provisioned storage."
                ),
                field="in_use_mib",
                source_refs=[ref("provisioned_mib"), ref("in_use_mib")],
            )
        )

    return findings


def _field(
    *,
    name: str,
    value: Any,
    raw_value: str | None,
    path: Path,
    source_type: str,
    row_number: int,
    column_name: str | None,
    parser: str,
    unit: str | None = None,
    confidence: str = "high",
    warnings: list[str] | None = None,
) -> EvidenceField:
    return EvidenceField(
        name=name,
        value=value,
        raw_value=clean_string(raw_value),
        unit=unit,
        source_ref=_source_ref(path, source_type, row_number, column_name),
        parser=parser,
        confidence=confidence,  # type: ignore[arg-type]
        warnings=warnings or [],
    )


def _parse_with_quality(
    parser,
    raw_value: str | None,
    *,
    field: str,
    row_number: int,
    warnings: list[str],
    data_quality: list[DataQualityFinding],
    source_ref: SourceRef,
) -> Any:
    before = len(warnings)
    value = parser(raw_value, field=field, row_number=row_number, warnings=warnings)
    for warning in warnings[before:]:
        data_quality.append(
            DataQualityFinding(
                code="PARSE_WARNING",
                severity="warning",
                message=warning,
                field=field,
                source_refs=[source_ref],
            )
        )
    return value


def _require_header(
    *,
    condition: bool,
    message: str,
    strict: bool,
    warnings: list[str],
    data_quality: list[DataQualityFinding],
    path: Path,
    source_type: str,
) -> None:
    if condition:
        return
    if strict:
        raise TriageError(message)
    warnings.append(message)
    data_quality.append(
        DataQualityFinding(
            code="MISSING_REQUIRED_COLUMN",
            severity="warning",
            message=message,
            source_refs=[SourceRef(source_type=source_type, path=str(path))],  # type: ignore[arg-type]
        )
    )


def read_inventory_evidence_csv(
    path: Path,
    *,
    strict: bool = False,
    mapping_spec: ColumnMapping | None = None,
) -> AdapterResult:
    headers, rows = _dict_reader(path)
    warnings: list[str] = []
    evidence_quality: list[DataQualityFinding] = []
    _header_quality(
        headers=headers,
        path=path,
        source_type="inventory",
        strict=strict,
        warnings=warnings,
        data_quality=evidence_quality,
    )
    if not headers:
        message = f"Inventory CSV {path} has no header row."
        if strict:
            raise TriageError(message)
        warnings.append(message)
        evidence_quality.append(
            DataQualityFinding(
                code="MISSING_HEADER",
                severity="warning",
                message=message,
                source_refs=[SourceRef(source_type="inventory", path=str(path))],
            )
        )
        return AdapterResult(
            adapter_id="inventory_csv",
            evidence=EvidenceSet(data_quality=evidence_quality),
            row_count=0,
            warnings=warnings,
        )

    mapping = (
        effective_mapping(kind="inventory", headers=headers, mapping=mapping_spec)
        if mapping_spec is not None
        else identify_columns(headers, INVENTORY_ALIASES)
    )
    _require_header(
        condition="name" in mapping,
        message="Inventory CSV is missing a workload name column.",
        strict=strict,
        warnings=warnings,
        data_quality=evidence_quality,
        path=path,
        source_type="inventory",
    )

    records: list[EvidenceRecord] = []
    for row_number, row in rows:
        data_quality: list[DataQualityFinding] = _row_shape_quality(
            row=row,
            path=path,
            source_type="inventory",
            row_number=row_number,
        )
        record_ref = _record_ref(path, "inventory", row_number)
        fields: dict[str, EvidenceField] = {}

        name_raw = _raw(row, mapping, "name")
        name = clean_string(name_raw) or ""
        normalized = normalize_name(name)
        uuid_raw = _raw(row, mapping, "uuid")
        uuid = normalize_uuid(uuid_raw)

        if strict and not (name or uuid):
            raise TriageError(f"Inventory row {row_number} has neither workload name nor UUID.")
        if not (name or uuid):
            message = f"Inventory row {row_number} has neither workload name nor UUID; skipped."
            warnings.append(message)
            evidence_quality.append(
                DataQualityFinding(
                    code="MISSING_IDENTITY",
                    severity="warning",
                    message=message,
                    source_refs=[record_ref],
                )
            )
            continue

        if "name" in mapping:
            fields["name"] = _field(
                name="name",
                value=name,
                raw_value=name_raw,
                path=path,
                source_type="inventory",
                row_number=row_number,
                column_name=mapping["name"],
                parser="clean_string",
            )
            fields["normalized_name"] = _field(
                name="normalized_name",
                value=normalized,
                raw_value=name_raw,
                path=path,
                source_type="inventory",
                row_number=row_number,
                column_name=mapping["name"],
                parser="normalize_name",
            )
        if "uuid" in mapping:
            fields["uuid"] = _field(
                name="uuid",
                value=uuid,
                raw_value=uuid_raw,
                path=path,
                source_type="inventory",
                row_number=row_number,
                column_name=mapping["uuid"],
                parser="normalize_uuid",
            )

        text_fields = [
            "power_state",
            "os",
            "datacenter",
            "cluster",
            "host",
            "tools_status",
            "tags",
            "notes",
        ]
        for canonical in text_fields:
            if canonical in mapping:
                fields[canonical] = _field(
                    name=canonical,
                    value=clean_string(_raw(row, mapping, canonical)),
                    raw_value=_raw(row, mapping, canonical),
                    path=path,
                    source_type="inventory",
                    row_number=row_number,
                    column_name=mapping[canonical],
                    parser="clean_string",
                )

        numeric_parsers = {
            "cpu_count": (parse_int, None),
            "memory_mib": (parse_mib, "MiB"),
            "provisioned_mib": (parse_mib, "MiB"),
            "in_use_mib": (parse_mib, "MiB"),
            "snapshot_total_mib": (parse_mib, "MiB"),
            "cpu_usage_pct": (parse_float, "percent"),
            "memory_usage_pct": (parse_float, "percent"),
        }
        for canonical, (parser, unit) in numeric_parsers.items():
            if canonical not in mapping:
                continue
            source_ref = _source_ref(path, "inventory", row_number, mapping[canonical])
            value = _parse_with_quality(
                parser,
                _raw(row, mapping, canonical),
                field=canonical,
                row_number=row_number,
                warnings=warnings,
                data_quality=data_quality,
                source_ref=source_ref,
            )
            fields[canonical] = _field(
                name=canonical,
                value=value,
                raw_value=_raw(row, mapping, canonical),
                path=path,
                source_type="inventory",
                row_number=row_number,
                column_name=mapping[canonical],
                parser=parser.__name__,
                unit=unit,
                confidence="low" if value is None and clean_string(_raw(row, mapping, canonical)) else "high",
            )

        for canonical in ("last_powered_on", "last_seen"):
            if canonical not in mapping:
                continue
            source_ref = _source_ref(path, "inventory", row_number, mapping[canonical])
            value = _parse_with_quality(
                parse_datetime,
                _raw(row, mapping, canonical),
                field=canonical,
                row_number=row_number,
                warnings=warnings,
                data_quality=data_quality,
                source_ref=source_ref,
            )
            fields[canonical] = _field(
                name=canonical,
                value=value,
                raw_value=_raw(row, mapping, canonical),
                path=path,
                source_type="inventory",
                row_number=row_number,
                column_name=mapping[canonical],
                parser="parse_datetime",
                unit="UTC",
                confidence="low" if value is None and clean_string(_raw(row, mapping, canonical)) else "high",
            )

        data_quality.extend(
            _numeric_range_quality(fields=fields, source_type="inventory", row_number=row_number)
        )
        records.append(
            EvidenceRecord(
                record_id=f"inventory:{row_number}",
                source_type="inventory",
                source_ref=record_ref,
                fields=fields,
                data_quality=data_quality,
            )
        )

    evidence = EvidenceSet(records=records, data_quality=evidence_quality)
    return AdapterResult(
        adapter_id="inventory_csv",
        evidence=evidence,
        row_count=len(records),
        warnings=warnings,
    )


def read_backup_evidence_csv(
    path: Path,
    *,
    strict: bool = False,
    mapping_spec: ColumnMapping | None = None,
) -> AdapterResult:
    headers, rows = _dict_reader(path)
    warnings: list[str] = []
    evidence_quality: list[DataQualityFinding] = []
    _header_quality(
        headers=headers,
        path=path,
        source_type="backup",
        strict=strict,
        warnings=warnings,
        data_quality=evidence_quality,
    )
    if not headers:
        message = f"Backup CSV {path} has no header row."
        if strict:
            raise TriageError(message)
        warnings.append(message)
        evidence_quality.append(
            DataQualityFinding(
                code="MISSING_HEADER",
                severity="warning",
                message=message,
                source_refs=[SourceRef(source_type="backup", path=str(path))],
            )
        )
        return AdapterResult(
            adapter_id="backup_csv",
            evidence=EvidenceSet(data_quality=evidence_quality),
            row_count=0,
            warnings=warnings,
        )

    mapping = (
        effective_mapping(kind="backup", headers=headers, mapping=mapping_spec)
        if mapping_spec is not None
        else identify_columns(headers, BACKUP_ALIASES)
    )
    _require_header(
        condition="name" in mapping or "uuid" in mapping,
        message="Backup CSV is missing both workload name and UUID columns.",
        strict=strict,
        warnings=warnings,
        data_quality=evidence_quality,
        path=path,
        source_type="backup",
    )
    size_fields = ("backup_total_mib", "latest_full_mib", "total_backup_mib")
    _require_header(
        condition=any(field in mapping for field in size_fields),
        message="Backup CSV is missing all backup size fields.",
        strict=strict,
        warnings=warnings,
        data_quality=evidence_quality,
        path=path,
        source_type="backup",
    )

    records: list[EvidenceRecord] = []
    for row_number, row in rows:
        data_quality: list[DataQualityFinding] = _row_shape_quality(
            row=row,
            path=path,
            source_type="backup",
            row_number=row_number,
        )
        record_ref = _record_ref(path, "backup", row_number)
        fields: dict[str, EvidenceField] = {}

        name_raw = _raw(row, mapping, "name")
        name = clean_string(name_raw)
        uuid_raw = _raw(row, mapping, "uuid")
        uuid = normalize_uuid(uuid_raw)

        if strict and not (name or uuid):
            raise TriageError(f"Backup row {row_number} has neither workload name nor UUID.")
        if not (name or uuid):
            message = f"Backup row {row_number} has neither workload name nor UUID; skipped."
            warnings.append(message)
            evidence_quality.append(
                DataQualityFinding(
                    code="MISSING_IDENTITY",
                    severity="warning",
                    message=message,
                    source_refs=[record_ref],
                )
            )
            continue

        if "name" in mapping:
            fields["name"] = _field(
                name="name",
                value=name,
                raw_value=name_raw,
                path=path,
                source_type="backup",
                row_number=row_number,
                column_name=mapping["name"],
                parser="clean_string",
            )
            fields["normalized_name"] = _field(
                name="normalized_name",
                value=normalize_name(name),
                raw_value=name_raw,
                path=path,
                source_type="backup",
                row_number=row_number,
                column_name=mapping["name"],
                parser="normalize_name",
            )
        if "uuid" in mapping:
            fields["uuid"] = _field(
                name="uuid",
                value=uuid,
                raw_value=uuid_raw,
                path=path,
                source_type="backup",
                row_number=row_number,
                column_name=mapping["uuid"],
                parser="normalize_uuid",
            )

        backup_total_mib = None
        backup_total_source = None
        for size_field in size_fields:
            if size_field not in mapping:
                continue
            source_ref = _source_ref(path, "backup", row_number, mapping[size_field])
            parsed = _parse_with_quality(
                parse_mib,
                _raw(row, mapping, size_field),
                field=size_field,
                row_number=row_number,
                warnings=warnings,
                data_quality=data_quality,
                source_ref=source_ref,
            )
            fields[size_field] = _field(
                name=size_field,
                value=parsed,
                raw_value=_raw(row, mapping, size_field),
                path=path,
                source_type="backup",
                row_number=row_number,
                column_name=mapping[size_field],
                parser="parse_mib",
                unit="MiB",
                confidence="low" if parsed is None and clean_string(_raw(row, mapping, size_field)) else "high",
            )
            if backup_total_mib is None and parsed is not None:
                backup_total_mib = parsed
                backup_total_source = size_field

        if backup_total_source is not None:
            fields["backup_total_mib"] = _field(
                name="backup_total_mib",
                value=backup_total_mib,
                raw_value=_raw(row, mapping, backup_total_source),
                path=path,
                source_type="backup",
                row_number=row_number,
                column_name=mapping[backup_total_source],
                parser=f"coalesce:{backup_total_source}",
                unit="MiB",
            )

        numeric_parsers = {
            "restore_point_count": (parse_int, None),
            "avg_daily_change_mib": (parse_mib, "MiB"),
            "latest_incremental_mib": (parse_mib, "MiB"),
            "retention_days": (parse_int, "days"),
            "rpo_hours": (parse_float, "hours"),
        }
        for canonical, (parser, unit) in numeric_parsers.items():
            if canonical not in mapping:
                continue
            source_ref = _source_ref(path, "backup", row_number, mapping[canonical])
            value = _parse_with_quality(
                parser,
                _raw(row, mapping, canonical),
                field=canonical,
                row_number=row_number,
                warnings=warnings,
                data_quality=data_quality,
                source_ref=source_ref,
            )
            fields[canonical] = _field(
                name=canonical,
                value=value,
                raw_value=_raw(row, mapping, canonical),
                path=path,
                source_type="backup",
                row_number=row_number,
                column_name=mapping[canonical],
                parser=parser.__name__,
                unit=unit,
                confidence="low" if value is None and clean_string(_raw(row, mapping, canonical)) else "high",
            )

        for canonical in (
            "latest_restore_point_utc",
            "immutable_until_utc",
            "last_success_utc",
            "last_failure_utc",
        ):
            if canonical not in mapping:
                continue
            source_ref = _source_ref(path, "backup", row_number, mapping[canonical])
            value = _parse_with_quality(
                parse_datetime,
                _raw(row, mapping, canonical),
                field=canonical,
                row_number=row_number,
                warnings=warnings,
                data_quality=data_quality,
                source_ref=source_ref,
            )
            fields[canonical] = _field(
                name=canonical,
                value=value,
                raw_value=_raw(row, mapping, canonical),
                path=path,
                source_type="backup",
                row_number=row_number,
                column_name=mapping[canonical],
                parser="parse_datetime",
                unit="UTC",
                confidence="low" if value is None and clean_string(_raw(row, mapping, canonical)) else "high",
            )

        for canonical in ("backup_job", "backup_policy", "rto_tier", "repository"):
            if canonical in mapping:
                fields[canonical] = _field(
                    name=canonical,
                    value=clean_string(_raw(row, mapping, canonical)),
                    raw_value=_raw(row, mapping, canonical),
                    path=path,
                    source_type="backup",
                    row_number=row_number,
                    column_name=mapping[canonical],
                    parser="clean_string",
                )

        if "protected" in mapping:
            fields["protected"] = _field(
                name="protected",
                value=parse_bool(_raw(row, mapping, "protected")),
                raw_value=_raw(row, mapping, "protected"),
                path=path,
                source_type="backup",
                row_number=row_number,
                column_name=mapping["protected"],
                parser="parse_bool",
            )

        data_quality.extend(
            _numeric_range_quality(fields=fields, source_type="backup", row_number=row_number)
        )
        records.append(
            EvidenceRecord(
                record_id=f"backup:{row_number}",
                source_type="backup",
                source_ref=record_ref,
                fields=fields,
                data_quality=data_quality,
            )
        )

    evidence = EvidenceSet(records=records, data_quality=evidence_quality)
    return AdapterResult(
        adapter_id="backup_csv",
        evidence=evidence,
        row_count=len(records),
        warnings=warnings,
    )


def read_utilization_evidence_csv(
    path: Path,
    *,
    strict: bool = False,
    mapping_spec: ColumnMapping | None = None,
) -> AdapterResult:
    headers, rows = _dict_reader(path)
    warnings: list[str] = []
    evidence_quality: list[DataQualityFinding] = []
    _header_quality(
        headers=headers,
        path=path,
        source_type="utilization",
        strict=strict,
        warnings=warnings,
        data_quality=evidence_quality,
    )
    if not headers:
        message = f"Utilization CSV {path} has no header row."
        if strict:
            raise TriageError(message)
        warnings.append(message)
        evidence_quality.append(
            DataQualityFinding(
                code="MISSING_HEADER",
                severity="warning",
                message=message,
                source_refs=[SourceRef(source_type="utilization", path=str(path))],
            )
        )
        return AdapterResult(
            adapter_id="utilization_csv",
            evidence=EvidenceSet(data_quality=evidence_quality),
            row_count=0,
            warnings=warnings,
        )

    mapping = (
        effective_mapping(kind="utilization", headers=headers, mapping=mapping_spec)
        if mapping_spec is not None
        else identify_columns(headers, UTILIZATION_ALIASES)
    )
    _require_header(
        condition="name" in mapping or "uuid" in mapping,
        message="Utilization CSV is missing both workload name and UUID columns.",
        strict=strict,
        warnings=warnings,
        data_quality=evidence_quality,
        path=path,
        source_type="utilization",
    )

    records: list[EvidenceRecord] = []
    for row_number, row in rows:
        data_quality: list[DataQualityFinding] = _row_shape_quality(
            row=row,
            path=path,
            source_type="utilization",
            row_number=row_number,
        )
        record_ref = _record_ref(path, "utilization", row_number)
        fields: dict[str, EvidenceField] = {}

        name_raw = _raw(row, mapping, "name")
        name = clean_string(name_raw)
        uuid_raw = _raw(row, mapping, "uuid")
        uuid = normalize_uuid(uuid_raw)
        if strict and not (name or uuid):
            raise TriageError(f"Utilization row {row_number} has neither workload name nor UUID.")
        if not (name or uuid):
            message = f"Utilization row {row_number} has neither workload name nor UUID; skipped."
            warnings.append(message)
            evidence_quality.append(
                DataQualityFinding(
                    code="MISSING_IDENTITY",
                    severity="warning",
                    message=message,
                    source_refs=[record_ref],
                )
            )
            continue

        if "name" in mapping:
            fields["name"] = _field(
                name="name",
                value=name,
                raw_value=name_raw,
                path=path,
                source_type="utilization",
                row_number=row_number,
                column_name=mapping["name"],
                parser="clean_string",
            )
            fields["normalized_name"] = _field(
                name="normalized_name",
                value=normalize_name(name),
                raw_value=name_raw,
                path=path,
                source_type="utilization",
                row_number=row_number,
                column_name=mapping["name"],
                parser="normalize_name",
            )
        if "uuid" in mapping:
            fields["uuid"] = _field(
                name="uuid",
                value=uuid,
                raw_value=uuid_raw,
                path=path,
                source_type="utilization",
                row_number=row_number,
                column_name=mapping["uuid"],
                parser="normalize_uuid",
            )

        for canonical in ("sample_start_utc", "sample_end_utc"):
            if canonical not in mapping:
                continue
            source_ref = _source_ref(path, "utilization", row_number, mapping[canonical])
            value = _parse_with_quality(
                parse_datetime,
                _raw(row, mapping, canonical),
                field=canonical,
                row_number=row_number,
                warnings=warnings,
                data_quality=data_quality,
                source_ref=source_ref,
            )
            fields[canonical] = _field(
                name=canonical,
                value=value,
                raw_value=_raw(row, mapping, canonical),
                path=path,
                source_type="utilization",
                row_number=row_number,
                column_name=mapping[canonical],
                parser="parse_datetime",
                unit="UTC",
                confidence="low" if value is None and clean_string(_raw(row, mapping, canonical)) else "high",
            )

        numeric_fields = {
            "cpu_avg_pct": (parse_float, "percent"),
            "cpu_p95_pct": (parse_float, "percent"),
            "cpu_max_pct": (parse_float, "percent"),
            "memory_avg_pct": (parse_float, "percent"),
            "memory_p95_pct": (parse_float, "percent"),
            "memory_max_pct": (parse_float, "percent"),
            "sample_count": (parse_int, None),
        }
        for canonical, (parser, unit) in numeric_fields.items():
            if canonical not in mapping:
                continue
            source_ref = _source_ref(path, "utilization", row_number, mapping[canonical])
            value = _parse_with_quality(
                parser,
                _raw(row, mapping, canonical),
                field=canonical,
                row_number=row_number,
                warnings=warnings,
                data_quality=data_quality,
                source_ref=source_ref,
            )
            if isinstance(value, (int, float)) and value < 0:
                data_quality.append(
                    DataQualityFinding(
                        code="NEGATIVE_VALUE",
                        severity="warning",
                        message=f"Negative value for {canonical} ignored by confidence scoring.",
                        field=canonical,
                        source_refs=[source_ref],
                    )
                )
            fields[canonical] = _field(
                name=canonical,
                value=value,
                raw_value=_raw(row, mapping, canonical),
                path=path,
                source_type="utilization",
                row_number=row_number,
                column_name=mapping[canonical],
                parser=parser.__name__,
                unit=unit,
                confidence="low" if value is None and clean_string(_raw(row, mapping, canonical)) else "high",
            )

        data_quality.extend(
            _numeric_range_quality(fields=fields, source_type="utilization", row_number=row_number)
        )
        records.append(
            EvidenceRecord(
                record_id=f"utilization:{row_number}",
                source_type="utilization",
                source_ref=record_ref,
                fields=fields,
                data_quality=data_quality,
            )
        )

    return AdapterResult(
        adapter_id="utilization_csv",
        evidence=EvidenceSet(records=records, data_quality=evidence_quality),
        row_count=len(records),
        warnings=warnings,
    )


def merge_evidence_sets(*sets: EvidenceSet) -> EvidenceSet:
    data_quality: list[DataQualityFinding] = []
    records: list[EvidenceRecord] = []
    for evidence_set in sets:
        records.extend(evidence_set.records)
        data_quality.extend(evidence_set.data_quality)
    return EvidenceSet(records=records, data_quality=data_quality)


def inventory_record_to_model(record: EvidenceRecord) -> WorkloadInventory:
    return WorkloadInventory(
        source_row=record.source_ref.row_number or 0,
        name=record.value("name") or "",
        normalized_name=record.value("normalized_name") or "",
        uuid=record.value("uuid"),
        power_state=record.value("power_state"),
        cpu_count=record.value("cpu_count"),
        memory_mib=record.value("memory_mib"),
        provisioned_mib=record.value("provisioned_mib"),
        in_use_mib=record.value("in_use_mib"),
        os=record.value("os"),
        datacenter=record.value("datacenter"),
        cluster=record.value("cluster"),
        host=record.value("host"),
        snapshot_total_mib=record.value("snapshot_total_mib"),
        tools_status=record.value("tools_status"),
        cpu_usage_pct=record.value("cpu_usage_pct"),
        memory_usage_pct=record.value("memory_usage_pct"),
        last_powered_on=record.value("last_powered_on"),
        last_seen=record.value("last_seen"),
        tags=record.value("tags"),
        notes=record.value("notes"),
    )


def backup_record_to_model(record: EvidenceRecord) -> BackupMetadata:
    return BackupMetadata(
        source_row=record.source_ref.row_number or 0,
        name=record.value("name"),
        normalized_name=record.value("normalized_name") or "",
        uuid=record.value("uuid"),
        backup_total_mib=record.value("backup_total_mib"),
        latest_restore_point_utc=record.value("latest_restore_point_utc"),
        restore_point_count=record.value("restore_point_count"),
        avg_daily_change_mib=record.value("avg_daily_change_mib"),
        latest_incremental_mib=record.value("latest_incremental_mib"),
        backup_job=record.value("backup_job"),
        backup_policy=record.value("backup_policy"),
        retention_days=record.value("retention_days"),
        immutable_until_utc=record.value("immutable_until_utc"),
        rpo_hours=record.value("rpo_hours"),
        rto_tier=record.value("rto_tier"),
        repository=record.value("repository"),
        protected=record.value("protected"),
        last_success_utc=record.value("last_success_utc"),
        last_failure_utc=record.value("last_failure_utc"),
    )
