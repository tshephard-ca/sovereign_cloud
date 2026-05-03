"""Validation reports for adapters and bundles."""

from __future__ import annotations

import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from pydantic import BaseModel, Field

from estate_triage.evidence import AdapterResult, DataQualityFinding


class ReadinessAction(BaseModel):
    severity: str
    field: str | None = None
    action: str
    reason: str


class DataRequestItem(BaseModel):
    field: str
    priority: str
    request: str
    reason: str


class FieldProfile(BaseModel):
    field: str
    mapped_header: str | None = None
    present: bool
    records_with_value: int = 0
    blank_pct: float = 100.0
    distinct_values: int = 0
    sample_values: list[str] = Field(default_factory=list)
    detected_units: list[str] = Field(default_factory=list)
    detected_date_formats: list[str] = Field(default_factory=list)
    mapping_confidence: str = "low"
    warnings: list[str] = Field(default_factory=list)


class MatchabilityForecast(BaseModel):
    records: int
    with_uuid: int = 0
    with_name: int = 0
    uuid_rate_pct: float = 0.0
    name_rate_pct: float = 0.0
    duplicate_uuid_values: int = 0
    duplicate_name_values: int = 0
    forecast: str = "low"


class MappingAlternative(BaseModel):
    field: str
    candidate_header: str
    confidence: float
    reason: str


class MappingApproval(BaseModel):
    approved: bool = False
    approved_by: str | None = None
    approved_at_utc: str | None = None
    approval_notes: str | None = None


class ValidationReport(BaseModel):
    input_kind: str
    path: str
    row_count: int
    recognized_records: int
    warnings: list[str] = Field(default_factory=list)
    data_quality: list[DataQualityFinding] = Field(default_factory=list)
    missing_recommended_fields: list[str] = Field(default_factory=list)
    unmapped_columns: list[str] = Field(default_factory=list)
    readiness_score: int = 100
    readiness_grade: str = "A"
    remediation_actions: list[ReadinessAction] = Field(default_factory=list)
    data_request_checklist: list[DataRequestItem] = Field(default_factory=list)
    business_severity_counts: dict[str, int] = Field(default_factory=dict)
    matchability_forecast: MatchabilityForecast | None = None
    field_profiles: list[FieldProfile] = Field(default_factory=list)
    mapping_alternatives: list[MappingAlternative] = Field(default_factory=list)
    mapping_approval: MappingApproval = Field(default_factory=MappingApproval)


RECOMMENDED_FIELDS = {
    "inventory": [
        "uuid",
        "power_state",
        "cpu_count",
        "memory_mib",
        "in_use_mib",
        "os",
    ],
    "backup": [
        "uuid",
        "latest_restore_point_utc",
        "restore_point_count",
        "avg_daily_change_mib",
        "backup_total_mib",
    ],
    "utilization": [
        "uuid",
        "sample_start_utc",
        "sample_end_utc",
        "cpu_p95_pct",
        "memory_p95_pct",
        "sample_count",
    ],
}


CANONICAL_ALIASES = {
    "inventory": {
        "name": ("vm", "name", "workload_name", "workload name"),
        "uuid": ("vm uuid", "uuid", "instance uuid", "bios_uuid"),
        "power_state": ("powerstate", "power state"),
        "cpu_count": ("cpus", "vcpus", "cpu count"),
        "memory_mib": ("memory", "memory mib", "ram mib"),
        "in_use_mib": ("in use mib", "used mib", "storage used mib"),
        "os": ("os", "guest os"),
    },
    "backup": {
        "name": ("vm", "name", "workload_name", "workload name"),
        "uuid": ("vm uuid", "uuid", "instance uuid", "bios_uuid"),
        "backup_total_mib": ("backup total mib", "backup_total_mib", "total backup mib"),
        "latest_restore_point_utc": ("latest restore point utc", "latest_restore_point_utc"),
        "restore_point_count": ("restore point count", "restore_point_count"),
        "avg_daily_change_mib": ("average daily change mib", "avg_daily_change_mib"),
    },
    "utilization": {
        "name": ("vm", "name", "workload_name", "workload name"),
        "uuid": ("vm uuid", "uuid", "instance uuid", "bios_uuid"),
        "sample_start_utc": ("sample start utc", "sample_start_utc"),
        "sample_end_utc": ("sample end utc", "sample_end_utc"),
        "cpu_p95_pct": ("cpu p95 percent", "cpu_p95_pct"),
        "memory_p95_pct": ("memory p95 percent", "memory_p95_pct"),
        "sample_count": ("sample count", "sample_count"),
    },
}


FIELD_IMPACT = {
    "inventory": {
        "uuid": "improves identity confidence and avoids name-only matches",
        "power_state": "improves archive and migration review accuracy",
        "cpu_count": "enables allocation review",
        "memory_mib": "enables allocation review",
        "in_use_mib": "enables storage ratios, change rates, and footprint rules",
        "os": "improves migration and archive confidence",
    },
    "backup": {
        "uuid": "improves identity confidence and avoids name-only matches",
        "latest_restore_point_utc": "enables recent and stale backup rules",
        "restore_point_count": "enables DR tier review signals",
        "avg_daily_change_mib": "enables change-rate calculation",
        "backup_total_mib": "enables backup footprint and backup-to-used ratio rules",
    },
    "utilization": {
        "uuid": "improves identity confidence and avoids name-only matches",
        "sample_start_utc": "qualifies the utilization observation window",
        "sample_end_utc": "qualifies the utilization observation window",
        "cpu_p95_pct": "enables utilization-backed CPU right-sizing review",
        "memory_p95_pct": "enables utilization-backed memory right-sizing review",
        "sample_count": "qualifies confidence in utilization aggregates",
    },
}


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def _quality_penalty(finding: DataQualityFinding) -> int:
    if finding.severity == "error":
        return 25
    if finding.severity == "warning":
        return 8
    return 2


def _business_severity(finding: DataQualityFinding) -> str:
    if finding.severity == "error":
        return "critical"
    if finding.code in {
        "MISSING_REQUIRED_COLUMN",
        "MISSING_HEADER",
        "DUPLICATE_INVENTORY_UUID",
        "DUPLICATE_BACKUP_UUID",
    }:
        return "critical"
    if finding.field in {
        "uuid",
        "backup_total_mib",
        "in_use_mib",
        "latest_restore_point_utc",
        "avg_daily_change_mib",
    }:
        return "high"
    if finding.code in {
        "IN_USE_EXCEEDS_PROVISIONED",
        "PERCENT_OUT_OF_RANGE",
        "MIXED_UNITS",
        "MIXED_DATE_FORMATS",
        "MAPPED_COLUMN_MOSTLY_BLANK",
    }:
        return "medium"
    return "low"


def _data_request_checklist(input_kind: str, missing_fields: list[str]) -> list[DataRequestItem]:
    high_priority = {
        "uuid",
        "in_use_mib",
        "backup_total_mib",
        "latest_restore_point_utc",
        "avg_daily_change_mib",
        "cpu_p95_pct",
        "memory_p95_pct",
    }
    return [
        DataRequestItem(
            field=field,
            priority="high" if field in high_priority else "medium",
            request=f"Provide or map `{field}` for {input_kind} input.",
            reason=FIELD_IMPACT.get(input_kind, {}).get(field, "Improves assessment confidence."),
        )
        for field in missing_fields
    ]


def _unit_kind(raw_value: str | None) -> str | None:
    if raw_value is None or not raw_value.strip():
        return None
    match = re.search(r"([kmgt](?:i?b)?|b|mib|gib|tib)\s*$", raw_value.strip().lower())
    return match.group(1) if match else "unitless"


def _date_format_kind(raw_value: str | None) -> str | None:
    if raw_value is None or not raw_value.strip():
        return None
    value = raw_value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", value):
        return "iso"
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", value):
        return "slash"
    if re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{4}", value):
        return "dotted"
    return "other"


def _field_profiles(
    *,
    input_kind: str,
    adapter_result: AdapterResult,
    mapped_fields: list[str],
    mapped_headers: list[str],
) -> tuple[list[FieldProfile], list[DataQualityFinding]]:
    records = adapter_result.evidence.records
    total = len(records)
    headers_by_field = dict(zip(mapped_fields, mapped_headers, strict=False))
    profiles: list[FieldProfile] = []
    findings: list[DataQualityFinding] = []
    storage_fields = {
        "memory_mib",
        "provisioned_mib",
        "in_use_mib",
        "snapshot_total_mib",
        "backup_total_mib",
        "latest_full_mib",
        "total_backup_mib",
        "avg_daily_change_mib",
        "latest_incremental_mib",
    }
    date_fields = {
        "last_powered_on",
        "last_seen",
        "latest_restore_point_utc",
        "immutable_until_utc",
        "last_success_utc",
        "last_failure_utc",
        "sample_start_utc",
        "sample_end_utc",
    }
    identifier_fields = {"uuid", "name"}
    category_fields = {
        "power_state",
        "os",
        "backup_policy",
        "rto_tier",
        "repository",
        "protected",
    }
    for field in mapped_fields:
        raw_values = [
            record.fields[field].raw_value
            for record in records
            if field in record.fields
        ]
        non_blank = [value for value in raw_values if value not in {None, ""}]
        distinct = sorted({str(value) for value in non_blank})
        blank_pct = round(((total - len(non_blank)) / total) * 100, 2) if total else 100.0
        units = sorted({unit for value in non_blank if (unit := _unit_kind(str(value)))})
        date_formats = sorted(
            {fmt for value in non_blank if (fmt := _date_format_kind(str(value)))}
        )
        warnings: list[str] = []
        source_refs = [
            record.fields[field].source_ref
            for record in records
            if field in record.fields
        ]
        if total and blank_pct >= 80:
            warnings.append("mostly_blank")
            findings.append(
                DataQualityFinding(
                    code="MAPPED_COLUMN_MOSTLY_BLANK",
                    severity="warning",
                    message=f"Mapped {field} column is {blank_pct}% blank.",
                    field=field,
                    source_refs=source_refs[:5],
                )
            )
        if field in storage_fields and len(units) > 1:
            warnings.append("mixed_units")
            findings.append(
                DataQualityFinding(
                    code="MIXED_UNITS",
                    severity="warning",
                    message=f"Mapped {field} column contains mixed units: {', '.join(units)}.",
                    field=field,
                    source_refs=source_refs[:5],
                )
            )
        if field in date_fields and len(date_formats) > 1:
            warnings.append("mixed_date_formats")
            findings.append(
                DataQualityFinding(
                    code="MIXED_DATE_FORMATS",
                    severity="warning",
                    message=f"Mapped {field} column contains mixed date formats: {', '.join(date_formats)}.",
                    field=field,
                    source_refs=source_refs[:5],
                )
            )
        if field in identifier_fields and total >= 10 and 0 < len(distinct) <= 1:
            warnings.append("low_cardinality_identifier")
            findings.append(
                DataQualityFinding(
                    code="LOW_CARDINALITY_IDENTIFIER",
                    severity="warning",
                    message=f"Mapped {field} column has too few distinct values for an identifier.",
                    field=field,
                    source_refs=source_refs[:5],
                )
            )
        if field in category_fields and total >= 10 and len(distinct) / total > 0.8:
            warnings.append("high_cardinality_category")
            findings.append(
                DataQualityFinding(
                    code="HIGH_CARDINALITY_CATEGORY",
                    severity="warning",
                    message=f"Mapped {field} column has unusually high cardinality for a category.",
                    field=field,
                    source_refs=source_refs[:5],
                )
            )
        confidence = "high"
        if warnings:
            confidence = "low" if any("cardinality" in warning for warning in warnings) else "medium"
        profiles.append(
            FieldProfile(
                field=field,
                mapped_header=headers_by_field.get(field),
                present=True,
                records_with_value=len(non_blank),
                blank_pct=blank_pct,
                distinct_values=len(distinct),
                sample_values=distinct[:3],
                detected_units=units,
                detected_date_formats=date_formats,
                mapping_confidence=confidence,
                warnings=warnings,
            )
        )
    return profiles, findings


def _matchability_forecast(adapter_result: AdapterResult) -> MatchabilityForecast:
    records = adapter_result.evidence.records
    total = len(records)
    uuids = [
        str(record.value("uuid"))
        for record in records
        if record.value("uuid")
    ]
    names = [
        str(record.value("normalized_name"))
        for record in records
        if record.value("normalized_name")
    ]
    uuid_counts = Counter(uuids)
    name_counts = Counter(names)
    duplicate_uuid_values = sum(1 for count in uuid_counts.values() if count > 1)
    duplicate_name_values = sum(1 for count in name_counts.values() if count > 1)
    uuid_rate = round((len(uuids) / total) * 100, 2) if total else 0.0
    name_rate = round((len(names) / total) * 100, 2) if total else 0.0
    forecast = "low"
    if uuid_rate >= 90 and duplicate_uuid_values == 0:
        forecast = "high"
    elif uuid_rate >= 50 or (name_rate >= 90 and duplicate_name_values == 0):
        forecast = "medium"
    return MatchabilityForecast(
        records=total,
        with_uuid=len(uuids),
        with_name=len(names),
        uuid_rate_pct=uuid_rate,
        name_rate_pct=name_rate,
        duplicate_uuid_values=duplicate_uuid_values,
        duplicate_name_values=duplicate_name_values,
        forecast=forecast,
    )


def _label_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


def _mapping_alternatives(
    *,
    input_kind: str,
    headers: list[str],
    mapped_fields: list[str],
) -> list[MappingAlternative]:
    aliases = CANONICAL_ALIASES.get(input_kind, {})
    alternatives: list[MappingAlternative] = []
    mapped = set(mapped_fields)
    candidate_fields = list(dict.fromkeys(["name", "uuid", *RECOMMENDED_FIELDS.get(input_kind, [])]))
    for field in candidate_fields:
        if field in mapped:
            continue
        candidates: list[tuple[float, str, str]] = []
        for header in headers:
            header_key = _label_key(header)
            if not header_key:
                continue
            for alias in aliases.get(field, (field,)):
                alias_key = _label_key(alias)
                ratio = SequenceMatcher(None, header_key, alias_key).ratio()
                if ratio >= 0.72:
                    candidates.append((round(ratio, 3), header, alias))
        if not candidates:
            continue
        confidence, header, alias = sorted(candidates, reverse=True)[0]
        alternatives.append(
            MappingAlternative(
                field=field,
                candidate_header=header,
                confidence=confidence,
                reason=f"Header resembles expected label {alias!r}.",
            )
        )
    return alternatives


def _readiness(
    *,
    input_kind: str,
    row_count: int,
    recognized_records: int,
    warnings: list[str],
    quality: list[DataQualityFinding],
    missing_recommended_fields: list[str],
) -> tuple[int, str, list[ReadinessAction]]:
    score = 100
    actions: list[ReadinessAction] = []

    if row_count == 0:
        score -= 60
        actions.append(
            ReadinessAction(
                severity="error",
                action="Provide a non-empty CSV export.",
                reason="No source rows were found.",
            )
        )
    elif recognized_records == 0:
        score -= 60
        actions.append(
            ReadinessAction(
                severity="error",
                action="Review the mapping file and required identifiers.",
                reason="No source rows could be normalized into canonical records.",
            )
        )
    else:
        recognized_ratio = recognized_records / row_count
        if recognized_ratio < 0.95:
            penalty = min(30, int((1 - recognized_ratio) * 50))
            score -= penalty
            actions.append(
                ReadinessAction(
                    severity="warning",
                    action="Review rows that were not normalized.",
                    reason=f"Only {recognized_records} of {row_count} rows became canonical records.",
                )
            )

    for field in missing_recommended_fields:
        score -= 8
        actions.append(
            ReadinessAction(
                severity="warning",
                field=field,
                action=f"Map or request `{field}` for {input_kind} input.",
                reason=FIELD_IMPACT.get(input_kind, {}).get(field, "Improves assessment confidence."),
            )
        )

    for warning in warnings:
        score -= 5
        actions.append(
            ReadinessAction(
                severity="warning",
                action="Review parser warning.",
                reason=warning,
            )
        )

    for finding in quality:
        score -= _quality_penalty(finding)
        actions.append(
            ReadinessAction(
                severity=finding.severity,
                field=finding.field,
                action="Fix or confirm the source value or mapping.",
                reason=f"{finding.code}: {finding.message}",
            )
        )

    score = max(0, min(100, score))
    return score, _grade(score), actions


def validation_report(
    *,
    input_kind: str,
    path: Path,
    adapter_result: AdapterResult,
    mapped_fields: list[str],
    headers: list[str],
    mapped_headers: list[str],
    mapping_approval: MappingApproval | None = None,
) -> ValidationReport:
    field_profiles, profile_findings = _field_profiles(
        input_kind=input_kind,
        adapter_result=adapter_result,
        mapped_fields=mapped_fields,
        mapped_headers=mapped_headers,
    )
    quality = [
        *adapter_result.evidence.data_quality,
        *[
            finding
            for record in adapter_result.evidence.records
            for finding in record.data_quality
        ],
        *profile_findings,
    ]
    missing_recommended_fields = [
        field
        for field in RECOMMENDED_FIELDS.get(input_kind, [])
        if field not in mapped_fields
    ]
    readiness_score, readiness_grade, remediation_actions = _readiness(
        input_kind=input_kind,
        row_count=adapter_result.row_count,
        recognized_records=len(adapter_result.evidence.records),
        warnings=adapter_result.warnings,
        quality=quality,
        missing_recommended_fields=missing_recommended_fields,
    )
    severity_counts = Counter(_business_severity(finding) for finding in quality)
    return ValidationReport(
        input_kind=input_kind,
        path=str(path),
        row_count=adapter_result.row_count,
        recognized_records=len(adapter_result.evidence.records),
        warnings=adapter_result.warnings,
        data_quality=quality,
        missing_recommended_fields=missing_recommended_fields,
        unmapped_columns=[header for header in headers if header not in set(mapped_headers)],
        readiness_score=readiness_score,
        readiness_grade=readiness_grade,
        remediation_actions=remediation_actions,
        data_request_checklist=_data_request_checklist(input_kind, missing_recommended_fields),
        business_severity_counts=dict(sorted(severity_counts.items())),
        matchability_forecast=_matchability_forecast(adapter_result),
        field_profiles=field_profiles,
        mapping_alternatives=_mapping_alternatives(
            input_kind=input_kind,
            headers=headers,
            mapped_fields=mapped_fields,
        ),
        mapping_approval=mapping_approval or MappingApproval(),
    )


def write_validation_report(path: Path, report: ValidationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
