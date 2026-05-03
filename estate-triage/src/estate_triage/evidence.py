"""Versioned evidence contracts for the assessment kernel."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from estate_triage.models import Confidence


EVIDENCE_SCHEMA_VERSION = "1.0.0"
FEATURE_SCHEMA_VERSION = "1.0.0"
POLICY_SCHEMA_VERSION = "1.0.0"
ASSESSMENT_SCHEMA_VERSION = "1.0.0"
TRACE_SCHEMA_VERSION = "1.0.0"

SourceType = Literal["inventory", "backup", "utilization", "unknown"]
Severity = Literal["info", "warning", "error"]


class SourceRef(BaseModel):
    """Precise provenance for a source value."""

    source_type: SourceType
    path: str
    row_number: int | None = None
    column_name: str | None = None


class DataQualityFinding(BaseModel):
    """Structured data-quality output independent of human report formats."""

    code: str
    severity: Severity = "warning"
    message: str
    field: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)


class EvidenceField(BaseModel):
    """One normalized value plus raw provenance."""

    name: str
    value: Any = None
    raw_value: str | None = None
    unit: str | None = None
    source_ref: SourceRef
    parser: str
    confidence: Confidence = "high"
    warnings: list[str] = Field(default_factory=list)


class EvidenceRecord(BaseModel):
    """A source row normalized into canonical evidence fields."""

    schema_version: str = EVIDENCE_SCHEMA_VERSION
    record_id: str
    source_type: SourceType
    source_ref: SourceRef
    fields: dict[str, EvidenceField] = Field(default_factory=dict)
    data_quality: list[DataQualityFinding] = Field(default_factory=list)

    def value(self, field: str) -> Any:
        evidence_field = self.fields.get(field)
        if evidence_field is None:
            return None
        return evidence_field.value

    def field_ref(self, field: str) -> SourceRef | None:
        evidence_field = self.fields.get(field)
        if evidence_field is None:
            return None
        return evidence_field.source_ref


class EvidenceSet(BaseModel):
    """A versioned bundle of normalized source evidence."""

    schema_version: str = EVIDENCE_SCHEMA_VERSION
    records: list[EvidenceRecord] = Field(default_factory=list)
    data_quality: list[DataQualityFinding] = Field(default_factory=list)
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def by_source_type(self, source_type: SourceType) -> list[EvidenceRecord]:
        return [record for record in self.records if record.source_type == source_type]


class AdapterResult(BaseModel):
    """Result emitted by an input adapter."""

    adapter_id: str
    adapter_version: str = "1.0.0"
    evidence: EvidenceSet
    row_count: int
    warnings: list[str] = Field(default_factory=list)
