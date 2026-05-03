"""Deterministic workload identity resolution."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from estate_triage.adapters import backup_record_to_model, inventory_record_to_model
from estate_triage.evidence import DataQualityFinding, EvidenceRecord, EvidenceSet, SourceRef
from estate_triage.models import BackupMetadata, MatchedBy, TriageError, WorkloadInventory


IdentityStatus = Literal[
    "RESOLVED",
    "PROBABLE",
    "CONFLICTED",
    "DUPLICATE_CANDIDATES",
    "UNMATCHED",
]


class IdentityTrace(BaseModel):
    status: IdentityStatus
    matched_by: MatchedBy
    strategy: str
    confidence: Literal["high", "medium", "low"]
    confidence_factors: dict[str, str] = Field(default_factory=dict)
    field_summary: str | None = None
    candidate_refs: list[SourceRef] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)


class ResolvedWorkload(BaseModel):
    workload_id: str
    status: IdentityStatus
    matched_by: MatchedBy
    inventory: WorkloadInventory
    backup: BackupMetadata | None = None
    inventory_record: EvidenceRecord
    backup_record: EvidenceRecord | None = None
    utilization_records: list[EvidenceRecord] = Field(default_factory=list)
    trace: IdentityTrace
    data_quality: list[DataQualityFinding] = Field(default_factory=list)


class IdentityResolutionResult(BaseModel):
    workloads: list[ResolvedWorkload]
    inventory_rows: int
    backup_rows: int
    utilization_rows: int = 0
    matched_by_uuid: int
    matched_by_name: int
    unmatched_inventory: int
    conflicted: int
    duplicate_candidates: int
    unmatched_backup_refs: list[SourceRef] = Field(default_factory=list)
    data_quality: list[DataQualityFinding] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class IdentityOverride(BaseModel):
    inventory_uuid: str | None = None
    inventory_name: str | None = None
    backup_uuid: str | None = None
    backup_name: str | None = None
    reason: str
    approved_by: str | None = None
    approved_at_utc: str | None = None


class IdentityOverrideSet(BaseModel):
    schema_version: str = "1.0.0"
    overrides: list[IdentityOverride] = Field(default_factory=list)


def load_identity_overrides(path: Path | None) -> IdentityOverrideSet | None:
    if path is None:
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise TriageError(f"Could not read identity override file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise TriageError(f"Could not parse identity override YAML {path}: {exc}") from exc
    try:
        overrides = IdentityOverrideSet(**raw)
    except Exception as exc:
        raise TriageError(f"Invalid identity override file {path}: {exc}") from exc
    for index, override in enumerate(overrides.overrides, start=1):
        if not (override.inventory_uuid or override.inventory_name):
            raise TriageError(f"Identity override {index} needs inventory_uuid or inventory_name.")
        if not (override.backup_uuid or override.backup_name):
            raise TriageError(f"Identity override {index} needs backup_uuid or backup_name.")
    return overrides


def _first_by_row(records: list[EvidenceRecord]) -> EvidenceRecord:
    return sorted(records, key=lambda record: record.source_ref.row_number or 0)[0]


def _index(records: list[EvidenceRecord], field: str) -> dict[str, list[EvidenceRecord]]:
    indexed: dict[str, list[EvidenceRecord]] = defaultdict(list)
    for record in records:
        value = record.value(field)
        if value:
            indexed[str(value)].append(record)
    return indexed


def _relaxed_name(value: str | None) -> str:
    if not value:
        return ""
    text = value.split("\\")[-1].split("/")[-1].split(".")[0]
    return "".join(character for character in text.lower() if character.isalnum())


def _relaxed_name_index(records: list[EvidenceRecord]) -> dict[str, list[EvidenceRecord]]:
    indexed: dict[str, list[EvidenceRecord]] = defaultdict(list)
    for record in records:
        relaxed = _relaxed_name(record.value("normalized_name"))
        if len(relaxed) >= 4:
            indexed[relaxed].append(record)
    return indexed


def _confidence_factors(
    *,
    status: IdentityStatus,
    matched_by: MatchedBy,
    strategy: str,
) -> dict[str, str]:
    identifier = "none"
    if matched_by == "UUID":
        identifier = "strong"
    elif matched_by == "NAME":
        identifier = "moderate" if strategy in {"normalized_name", "identity_override"} else "weak"
    conflict = "clear" if status not in {"CONFLICTED", "DUPLICATE_CANDIDATES"} else "conflicted"
    context = "not_used"
    if strategy == "identity_override":
        context = "reviewed_override"
    elif strategy == "controlled_relaxed_name":
        context = "relaxed_name_only"
    return {
        "identifier": identifier,
        "context": context,
        "conflict": conflict,
    }


def _field_summary(*, status: IdentityStatus, matched_by: MatchedBy, strategy: str) -> str:
    if strategy == "identity_override":
        return "Reviewed identity override selected the backup row."
    if strategy == "controlled_relaxed_name":
        return "Unique relaxed-name match selected the backup row; review before relying on it."
    if status == "CONFLICTED":
        return "UUID and name pointed to different backup rows; UUID was preferred."
    if status == "DUPLICATE_CANDIDATES":
        return "Multiple candidate rows exist; review identity evidence before presenting."
    if matched_by == "UUID":
        return "UUID matched inventory to backup."
    if matched_by == "NAME":
        return "Normalized name matched inventory to backup."
    return "No matching backup row was found."


def _override_key_for_inventory(inventory: WorkloadInventory) -> tuple[str, str] | None:
    if inventory.uuid:
        return ("uuid", inventory.uuid)
    if inventory.normalized_name:
        return ("name", inventory.normalized_name)
    return None


def _override_lookup(overrides: IdentityOverrideSet | None) -> dict[tuple[str, str], IdentityOverride]:
    lookup: dict[tuple[str, str], IdentityOverride] = {}
    if overrides is None:
        return lookup
    for override in overrides.overrides:
        if override.inventory_uuid:
            lookup[("uuid", override.inventory_uuid.strip().lower())] = override
        if override.inventory_name:
            from estate_triage.normalize import normalize_name

            lookup[("name", normalize_name(override.inventory_name))] = override
    return lookup


def _backup_record_for_override(
    override: IdentityOverride,
    *,
    backups_by_uuid: dict[str, list[EvidenceRecord]],
    backups_by_name: dict[str, list[EvidenceRecord]],
) -> tuple[EvidenceRecord | None, MatchedBy]:
    if override.backup_uuid:
        candidates = backups_by_uuid.get(override.backup_uuid.strip().lower(), [])
        if candidates:
            return _first_by_row(candidates), "UUID"
    if override.backup_name:
        from estate_triage.normalize import normalize_name

        candidates = backups_by_name.get(normalize_name(override.backup_name), [])
        if candidates:
            return _first_by_row(candidates), "NAME"
    return None, "NONE"


def _duplicate_findings(
    index: dict[str, list[EvidenceRecord]],
    *,
    field: str,
    source_type: str,
) -> list[DataQualityFinding]:
    findings: list[DataQualityFinding] = []
    for _value, records in index.items():
        if len(records) <= 1:
            continue
        severity: Literal["warning", "error"] = "error" if field == "uuid" else "warning"
        findings.append(
            DataQualityFinding(
                code=f"DUPLICATE_{source_type.upper()}_{field.upper()}",
                severity=severity,
                message=(
                    f"Duplicate {source_type} {field} values detected; "
                    "first source row is used for deterministic matching."
                ),
                field=field,
                source_refs=[record.source_ref for record in records],
            )
        )
    return findings


def resolve_identities(
    evidence: EvidenceSet,
    *,
    overrides: IdentityOverrideSet | None = None,
) -> IdentityResolutionResult:
    inventory_records = evidence.by_source_type("inventory")
    backup_records = evidence.by_source_type("backup")
    utilization_records = evidence.by_source_type("utilization")
    inventory_by_uuid = _index(inventory_records, "uuid")
    inventory_by_name = _index(inventory_records, "normalized_name")
    backups_by_uuid = _index(backup_records, "uuid")
    backups_by_name = _index(backup_records, "normalized_name")
    backups_by_relaxed_name = _relaxed_name_index(backup_records)
    utilization_by_uuid = _index(utilization_records, "uuid")
    utilization_by_name = _index(utilization_records, "normalized_name")
    overrides_by_inventory = _override_lookup(overrides)

    data_quality = [
        *_duplicate_findings(inventory_by_uuid, field="uuid", source_type="inventory"),
        *_duplicate_findings(inventory_by_name, field="name", source_type="inventory"),
        *_duplicate_findings(backups_by_uuid, field="uuid", source_type="backup"),
        *_duplicate_findings(backups_by_name, field="name", source_type="backup"),
    ]
    warnings = [finding.message for finding in data_quality]
    used_backup_ids: set[str] = set()
    workloads: list[ResolvedWorkload] = []

    for inventory_record in inventory_records:
        inventory = inventory_record_to_model(inventory_record)
        uuid_candidates = backups_by_uuid.get(inventory.uuid or "", [])
        name_candidates = backups_by_name.get(inventory.normalized_name or "", [])
        relaxed_candidates = backups_by_relaxed_name.get(_relaxed_name(inventory.normalized_name), [])
        duplicate_inventory_uuid = bool(
            inventory.uuid and len(inventory_by_uuid.get(inventory.uuid, [])) > 1
        )
        duplicate_inventory_name = bool(
            not inventory.uuid
            and inventory.normalized_name
            and len(inventory_by_name.get(inventory.normalized_name, [])) > 1
        )
        backup_record: EvidenceRecord | None = None
        matched_by: MatchedBy = "NONE"
        status: IdentityStatus = "UNMATCHED"
        strategy = "no_match"
        confidence: Literal["high", "medium", "low"] = "low"
        messages: list[str] = []
        row_quality: list[DataQualityFinding] = []
        override = overrides_by_inventory.get(_override_key_for_inventory(inventory) or ("", ""))

        if override is not None:
            backup_record, matched_by = _backup_record_for_override(
                override,
                backups_by_uuid=backups_by_uuid,
                backups_by_name=backups_by_name,
            )
            if backup_record is not None:
                status = "RESOLVED" if matched_by == "UUID" else "PROBABLE"
                strategy = "identity_override"
                confidence = "high" if matched_by == "UUID" else "medium"
                messages.append("Identity override applied.")
                row_quality.append(
                    DataQualityFinding(
                        code="IDENTITY_OVERRIDE_APPLIED",
                        severity="info",
                        message=f"Identity override applied: {override.reason}",
                        source_refs=[
                            inventory_record.source_ref,
                            backup_record.source_ref,
                        ],
                    )
                )
            else:
                row_quality.append(
                    DataQualityFinding(
                        code="IDENTITY_OVERRIDE_UNRESOLVED",
                        severity="warning",
                        message=f"Identity override could not find the requested backup row: {override.reason}",
                        source_refs=[inventory_record.source_ref],
                    )
                )
        elif uuid_candidates:
            backup_record = _first_by_row(uuid_candidates)
            matched_by = "UUID"
            status = "RESOLVED"
            strategy = "exact_uuid"
            confidence = "high"
            if len(uuid_candidates) > 1:
                status = "DUPLICATE_CANDIDATES"
                confidence = "low"
                row_quality.append(
                    DataQualityFinding(
                        code="DUPLICATE_UUID_CANDIDATES",
                        severity="warning",
                        message="Multiple backup rows share the matched UUID.",
                        field="uuid",
                        source_refs=[record.source_ref for record in uuid_candidates],
                    )
                )
            if name_candidates:
                name_match = _first_by_row(name_candidates)
                if name_match.record_id != backup_record.record_id:
                    status = "CONFLICTED"
                    confidence = "low"
                    strategy = "uuid_preferred_over_conflicting_name"
                    messages.append("UUID match preferred over conflicting name match.")
                    row_quality.append(
                        DataQualityFinding(
                            code="UUID_NAME_CONFLICT",
                            severity="warning",
                            message="UUID match and name match point to different backup rows; UUID was preferred.",
                            source_refs=[
                                inventory_record.source_ref,
                                backup_record.source_ref,
                                name_match.source_ref,
                            ],
                        )
                    )
        elif name_candidates:
            backup_record = _first_by_row(name_candidates)
            matched_by = "NAME"
            status = "PROBABLE"
            strategy = "normalized_name"
            confidence = "medium"
            if len(name_candidates) > 1:
                status = "DUPLICATE_CANDIDATES"
                confidence = "low"
                row_quality.append(
                    DataQualityFinding(
                        code="DUPLICATE_NAME_CANDIDATES",
                        severity="warning",
                        message="Multiple backup rows share the matched normalized name.",
                        field="normalized_name",
                        source_refs=[record.source_ref for record in name_candidates],
                    )
                )
        elif relaxed_candidates and len(relaxed_candidates) == 1:
            backup_record = _first_by_row(relaxed_candidates)
            matched_by = "NAME"
            status = "PROBABLE"
            strategy = "controlled_relaxed_name"
            confidence = "low"
            row_quality.append(
                DataQualityFinding(
                    code="CONTROLLED_FUZZY_NAME_MATCH",
                    severity="warning",
                    message="Unique relaxed-name match used after exact name and UUID matching failed.",
                    field="normalized_name",
                    source_refs=[inventory_record.source_ref, backup_record.source_ref],
                )
            )
        else:
            row_quality.append(
                DataQualityFinding(
                    code="UNMATCHED_INVENTORY",
                    severity="warning",
                    message="Inventory row did not match a backup row.",
                    source_refs=[inventory_record.source_ref],
                )
            )

        if duplicate_inventory_uuid:
            status = "DUPLICATE_CANDIDATES"
            confidence = "low"
            row_quality.append(
                DataQualityFinding(
                    code="DUPLICATE_INVENTORY_UUID",
                    severity="error",
                    message="Multiple inventory rows share this UUID.",
                    field="uuid",
                    source_refs=[
                        record.source_ref
                        for record in inventory_by_uuid.get(inventory.uuid or "", [])
                    ],
                )
            )
        elif duplicate_inventory_name:
            status = "DUPLICATE_CANDIDATES"
            confidence = "low"
            row_quality.append(
                DataQualityFinding(
                    code="DUPLICATE_INVENTORY_NAME",
                    severity="warning",
                    message="Multiple inventory rows share this normalized name without UUIDs.",
                    field="normalized_name",
                    source_refs=[
                        record.source_ref
                        for record in inventory_by_name.get(inventory.normalized_name or "", [])
                    ],
                )
            )

        backup = backup_record_to_model(backup_record) if backup_record else None
        if backup_record is not None:
            used_backup_ids.add(backup_record.record_id)

        candidate_refs = []
        if backup_record is not None:
            candidate_refs.append(backup_record.source_ref)
        matched_utilization = utilization_by_uuid.get(inventory.uuid or "")
        if not matched_utilization:
            matched_utilization = utilization_by_name.get(inventory.normalized_name or "", [])
        candidate_refs.extend(record.source_ref for record in matched_utilization)

        workloads.append(
            ResolvedWorkload(
                workload_id=inventory.uuid or inventory.normalized_name or f"inventory:{inventory.source_row}",
                status=status,
                matched_by=matched_by,
                inventory=inventory,
                backup=backup,
                inventory_record=inventory_record,
                backup_record=backup_record,
                utilization_records=matched_utilization,
                trace=IdentityTrace(
                    status=status,
                    matched_by=matched_by,
                    strategy=strategy,
                    confidence=confidence,
                    confidence_factors=_confidence_factors(
                        status=status,
                        matched_by=matched_by,
                        strategy=strategy,
                    ),
                    field_summary=_field_summary(
                        status=status,
                        matched_by=matched_by,
                        strategy=strategy,
                    ),
                    candidate_refs=candidate_refs,
                    messages=messages,
                ),
                data_quality=row_quality,
            )
        )

    unmatched_backup_refs = [
        record.source_ref for record in backup_records if record.record_id not in used_backup_ids
    ]
    if unmatched_backup_refs:
        data_quality.append(
            DataQualityFinding(
                code="UNMATCHED_BACKUP_ROWS",
                severity="info",
                message="Backup rows not matched to inventory were ignored for workload scoring.",
                source_refs=unmatched_backup_refs,
            )
        )
        data_quality.append(
            DataQualityFinding(
                code="UNMATCHED_BACKUP_LIKELY_DECOMMISSIONED",
                severity="info",
                message=(
                    "Unmatched backup rows may represent decommissioned, renamed, or otherwise "
                    "missing inventory workloads."
                ),
                source_refs=unmatched_backup_refs,
            )
        )

    return IdentityResolutionResult(
        workloads=workloads,
        inventory_rows=len(inventory_records),
        backup_rows=len(backup_records),
        utilization_rows=len(utilization_records),
        matched_by_uuid=sum(1 for workload in workloads if workload.matched_by == "UUID"),
        matched_by_name=sum(1 for workload in workloads if workload.matched_by == "NAME"),
        unmatched_inventory=sum(1 for workload in workloads if workload.matched_by == "NONE"),
        conflicted=sum(1 for workload in workloads if workload.status == "CONFLICTED"),
        duplicate_candidates=sum(1 for workload in workloads if workload.status == "DUPLICATE_CANDIDATES"),
        unmatched_backup_refs=unmatched_backup_refs,
        data_quality=data_quality,
        warnings=warnings,
    )


def identity_graph_payload(result: IdentityResolutionResult) -> dict:
    nodes: list[dict] = []
    edges: list[dict] = []
    for workload in result.workloads:
        inventory_id = f"inventory:{workload.inventory_record.record_id}"
        nodes.append(
            {
                "id": inventory_id,
                "kind": "inventory",
                "workload_id": workload.workload_id,
                "source_ref": workload.inventory_record.source_ref.model_dump(mode="json"),
            }
        )
        if workload.backup_record is not None:
            backup_id = f"backup:{workload.backup_record.record_id}"
            nodes.append(
                {
                    "id": backup_id,
                    "kind": "backup",
                    "workload_id": workload.workload_id,
                    "source_ref": workload.backup_record.source_ref.model_dump(mode="json"),
                }
            )
            edges.append(
                {
                    "from": inventory_id,
                    "to": backup_id,
                    "matched_by": workload.matched_by,
                    "status": workload.status,
                    "strategy": workload.trace.strategy,
                    "confidence": workload.trace.confidence,
                    "confidence_factors": workload.trace.confidence_factors,
                }
            )
    return {
        "schema_version": "1.0.0",
        "summary": {
            "inventory_rows": result.inventory_rows,
            "backup_rows": result.backup_rows,
            "matched_by_uuid": result.matched_by_uuid,
            "matched_by_name": result.matched_by_name,
            "unmatched_inventory": result.unmatched_inventory,
            "conflicted": result.conflicted,
            "duplicate_candidates": result.duplicate_candidates,
        },
        "nodes": nodes,
        "edges": edges,
        "data_quality": [finding.model_dump(mode="json") for finding in result.data_quality],
    }
