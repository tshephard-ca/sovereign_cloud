"""Validated data models used by the triage pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


MatchedBy = Literal["UUID", "NAME", "NONE"]
PrimaryMotion = Literal[
    "MIGRATION_REVIEW",
    "ARCHIVE_REVIEW",
    "RIGHTSIZING_REVIEW",
    "DR_TIER_REVIEW",
]
Confidence = Literal["high", "medium", "low"]


class TriageError(Exception):
    """Raised for strict-mode or unrecoverable input errors."""


class WorkloadInventory(BaseModel):
    source_row: int
    name: str = ""
    normalized_name: str = ""
    uuid: str | None = None
    power_state: str | None = None
    cpu_count: int | None = None
    memory_mib: float | None = None
    provisioned_mib: float | None = None
    in_use_mib: float | None = None
    os: str | None = None
    datacenter: str | None = None
    cluster: str | None = None
    host: str | None = None
    snapshot_total_mib: float | None = None
    tools_status: str | None = None
    cpu_usage_pct: float | None = None
    memory_usage_pct: float | None = None
    last_powered_on: datetime | None = None
    last_seen: datetime | None = None
    tags: str | None = None
    notes: str | None = None


class BackupMetadata(BaseModel):
    source_row: int
    name: str | None = None
    normalized_name: str = ""
    uuid: str | None = None
    backup_total_mib: float | None = None
    latest_restore_point_utc: datetime | None = None
    restore_point_count: int | None = None
    avg_daily_change_mib: float | None = None
    latest_incremental_mib: float | None = None
    backup_job: str | None = None
    backup_policy: str | None = None
    retention_days: int | None = None
    immutable_until_utc: datetime | None = None
    rpo_hours: float | None = None
    rto_tier: str | None = None
    repository: str | None = None
    protected: bool | None = None
    last_success_utc: datetime | None = None
    last_failure_utc: datetime | None = None


class JoinedWorkload(BaseModel):
    inventory: WorkloadInventory
    backup: BackupMetadata | None = None
    matched_by: MatchedBy
    warnings: list[str] = Field(default_factory=list)


class DerivedFeatures(BaseModel):
    workload_key: str
    backup_to_used_ratio: float | None = None
    change_rate_pct: float | None = None
    has_recent_backup: bool = False
    stale_backup: bool = False
    powered_on: bool = False
    powered_off: bool = False
    high_allocated_cpu: bool = False
    high_allocated_memory: bool = False
    large_backup_footprint: bool = False
    low_change_rate: bool = False
    snapshot_present: bool = False
    missing_data: list[str] = Field(default_factory=list)


class MotionScore(BaseModel):
    motion: PrimaryMotion
    score: int
    reason_codes: list[str] = Field(default_factory=list)
    reason_text: list[str] = Field(default_factory=list)
    allocation_only_rightsizing: bool = False


class TriageResult(BaseModel):
    rank: int = 0
    workload_key: str
    workload_name: str
    matched_by: MatchedBy
    primary_motion: PrimaryMotion
    opportunity_score: int
    confidence: Confidence
    reason_codes: list[str]
    reason_text: str
    blocking_flags: list[str]
    missing_data: list[str]
    power_state: str | None = None
    cpu_count: int | None = None
    memory_mib: float | None = None
    provisioned_mib: float | None = None
    in_use_mib: float | None = None
    os: str | None = None
    latest_restore_point_utc: datetime | None = None
    restore_point_count: int | None = None
    backup_total_mib: float | None = None
    avg_daily_change_mib: float | None = None
    change_rate_pct: float | None = None
    backup_to_used_ratio: float | None = None
    source_inventory_row: int
    source_backup_row: int | None = None
