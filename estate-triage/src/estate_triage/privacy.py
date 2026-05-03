"""Privacy helpers for structured assessment results."""

from __future__ import annotations

import hashlib
from typing import Literal

from estate_triage.assessment import AssessmentResult

PrivacyMode = Literal["minimal", "standard", "strict"]

STANDARD_FIELDS = {
    "datacenter",
    "cluster",
    "host",
    "tags",
    "notes",
    "backup_job",
    "backup_policy",
    "repository",
}


def stable_hash(value: str, *, salt: str = "") -> str:
    return hashlib.sha256(f"{salt}{value}".encode("utf-8")).hexdigest()[:12]


def redact_assessment(
    assessment: AssessmentResult,
    *,
    salt: str = "",
    mode: PrivacyMode = "minimal",
) -> AssessmentResult:
    """Return a redacted copy of an assessment result.

    Structured traces retain source row/column provenance, but workload names and keys are
    replaced so assessment JSON can be shared without exposing workload identifiers.
    """
    redacted = assessment.model_copy(deep=True)
    name_map: dict[str, str] = {}
    for workload in redacted.workloads:
        original_name = workload.workload_name or ""
        if original_name not in name_map:
            name_map[original_name] = f"workload_{len(name_map) + 1:03d}"
        redacted_name = name_map[original_name]
        redacted_key = stable_hash(workload.workload_key, salt=salt)
        workload.workload_key = redacted_key
        workload.workload_name = redacted_name
        workload.workload_id = redacted_key
        workload.feature_set.workload_id = redacted_key
        if "workload_key" in workload.feature_set.features:
            workload.feature_set.features["workload_key"].value = redacted_key
        workload.identity.workload_id = redacted_key
        workload.identity.inventory.name = redacted_name
        workload.identity.inventory.normalized_name = redacted_name
        if workload.identity.inventory.uuid is not None:
            workload.identity.inventory.uuid = stable_hash(workload.identity.inventory.uuid, salt=salt)
        if workload.identity.backup is not None:
            workload.identity.backup.name = redacted_name
            workload.identity.backup.normalized_name = redacted_name
            if workload.identity.backup.uuid is not None:
                workload.identity.backup.uuid = stable_hash(workload.identity.backup.uuid, salt=salt)
        if mode in {"standard", "strict"}:
            for field in STANDARD_FIELDS:
                if hasattr(workload.identity.inventory, field):
                    setattr(workload.identity.inventory, field, None)
                if workload.identity.backup is not None and hasattr(workload.identity.backup, field):
                    setattr(workload.identity.backup, field, None)
        for record in (
            workload.identity.inventory_record,
            workload.identity.backup_record,
            *workload.identity.utilization_records,
        ):
            if record is None:
                continue
            if mode == "strict":
                record.source_ref.path = "<redacted>"
            if mode in {"standard", "strict"}:
                for field in STANDARD_FIELDS:
                    if field in record.fields:
                        record.fields[field].value = None
                        record.fields[field].raw_value = None
            if "name" in record.fields:
                record.fields["name"].value = redacted_name
                record.fields["name"].raw_value = redacted_name
            if "normalized_name" in record.fields:
                record.fields["normalized_name"].value = redacted_name
                record.fields["normalized_name"].raw_value = redacted_name
            if "uuid" in record.fields and record.fields["uuid"].value is not None:
                hashed_uuid = stable_hash(str(record.fields["uuid"].value), salt=salt)
                record.fields["uuid"].value = hashed_uuid
                record.fields["uuid"].raw_value = hashed_uuid
            if mode == "strict":
                for evidence_field in record.fields.values():
                    evidence_field.source_ref.path = "<redacted>"
                    if isinstance(evidence_field.value, str) and evidence_field.name not in {
                        "name",
                        "normalized_name",
                        "uuid",
                    }:
                        evidence_field.value = "<redacted>"
                    if evidence_field.raw_value is not None and evidence_field.name not in {
                        "name",
                        "normalized_name",
                        "uuid",
                    }:
                        evidence_field.raw_value = "<redacted>"
        if mode == "strict":
            for feature in workload.feature_set.features.values():
                for source_ref in feature.source_refs:
                    source_ref.path = "<redacted>"
            for finding in [*workload.data_quality, *redacted.data_quality]:
                finding.message = "<redacted>"
                for source_ref in finding.source_refs:
                    source_ref.path = "<redacted>"
    return redacted
