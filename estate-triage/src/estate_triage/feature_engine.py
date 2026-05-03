"""Versioned feature registry for the assessment kernel."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from estate_triage.config import Thresholds
from estate_triage.evidence import FEATURE_SCHEMA_VERSION, SourceRef
from estate_triage.identity import ResolvedWorkload
from estate_triage.models import DerivedFeatures


class FeatureValue(BaseModel):
    name: str
    version: str
    value: Any = None
    required_evidence: list[str] = Field(default_factory=list)
    optional_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    confidence_impact: str = "none"
    trace: str


class FeatureSet(BaseModel):
    schema_version: str = FEATURE_SCHEMA_VERSION
    workload_id: str
    features: dict[str, FeatureValue]
    missing_evidence: list[str] = Field(default_factory=list)
    confidence_summary: dict[str, int] = Field(default_factory=dict)

    def value(self, name: str) -> Any:
        feature = self.features.get(name)
        if feature is None:
            return None
        return feature.value


@dataclass(frozen=True)
class FeatureCalculator:
    name: str
    version: str
    required_evidence: tuple[str, ...]
    optional_evidence: tuple[str, ...]
    compute: Callable[["FeatureContext"], FeatureValue]


class FeatureContext:
    def __init__(
        self,
        workload: ResolvedWorkload,
        thresholds: Thresholds,
        *,
        now: datetime | None,
        features: dict[str, FeatureValue],
    ) -> None:
        self.workload = workload
        self.thresholds = thresholds
        self.now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self.features = features

    def source_refs(self, *fields: str) -> list[SourceRef]:
        refs: list[SourceRef] = []
        for field in fields:
            if self.workload.inventory_record.field_ref(field) is not None:
                refs.append(self.workload.inventory_record.field_ref(field))  # type: ignore[arg-type]
            if self.workload.backup_record is not None and self.workload.backup_record.field_ref(field) is not None:
                refs.append(self.workload.backup_record.field_ref(field))  # type: ignore[arg-type]
            for record in self.workload.utilization_records:
                if record.field_ref(field) is not None:
                    refs.append(record.field_ref(field))  # type: ignore[arg-type]
        return refs


def _feature(
    *,
    name: str,
    version: str,
    value: Any,
    required: tuple[str, ...] = (),
    optional: tuple[str, ...] = (),
    missing: list[str] | None = None,
    source_refs: list[SourceRef] | None = None,
    trace: str,
    confidence_impact: str = "none",
) -> FeatureValue:
    return FeatureValue(
        name=name,
        version=version,
        value=value,
        required_evidence=list(required),
        optional_evidence=list(optional),
        missing_evidence=missing or [],
        source_refs=source_refs or [],
        trace=trace,
        confidence_impact=confidence_impact,
    )


def _workload_key(ctx: FeatureContext) -> FeatureValue:
    inventory = ctx.workload.inventory
    value = inventory.uuid or inventory.normalized_name
    return _feature(
        name="workload_key",
        version="1",
        value=value,
        required=("uuid|normalized_name",),
        source_refs=ctx.source_refs("uuid", "normalized_name"),
        trace="Prefer UUID when present; otherwise use normalized workload name.",
    )


def _backup_matched(ctx: FeatureContext) -> FeatureValue:
    return _feature(
        name="backup_matched",
        version="1",
        value=ctx.workload.backup is not None,
        trace="True when identity resolution attached a backup row.",
    )


def _backup_to_used_ratio(ctx: FeatureContext) -> FeatureValue:
    backup = ctx.workload.backup
    inventory = ctx.workload.inventory
    missing: list[str] = []
    if inventory.in_use_mib is None or inventory.in_use_mib <= 0:
        missing.append("in_use_mib")
        value = None
    elif backup is None or backup.backup_total_mib is None:
        missing.append("backup_total_mib")
        value = None
    else:
        value = backup.backup_total_mib / inventory.in_use_mib
    return _feature(
        name="backup_to_used_ratio",
        version="1",
        value=value,
        required=("backup_total_mib", "in_use_mib"),
        missing=missing,
        source_refs=ctx.source_refs("backup_total_mib", "in_use_mib"),
        trace="backup_total_mib / in_use_mib; unavailable when in-use storage is missing or zero.",
        confidence_impact="lowers_confidence" if missing else "none",
    )


def _change_rate_pct(ctx: FeatureContext) -> FeatureValue:
    backup = ctx.workload.backup
    inventory = ctx.workload.inventory
    missing: list[str] = []
    if inventory.in_use_mib is None or inventory.in_use_mib <= 0:
        missing.append("in_use_mib")
        value = None
    elif backup is None or backup.avg_daily_change_mib is None or backup.avg_daily_change_mib <= 0:
        missing.append("avg_daily_change_mib")
        value = None
    else:
        value = (backup.avg_daily_change_mib / inventory.in_use_mib) * 100
    return _feature(
        name="change_rate_pct",
        version="1",
        value=value,
        required=("avg_daily_change_mib", "in_use_mib"),
        missing=missing,
        source_refs=ctx.source_refs("avg_daily_change_mib", "in_use_mib"),
        trace="avg_daily_change_mib / in_use_mib * 100; unavailable when either input is missing or zero.",
        confidence_impact="lowers_confidence" if missing else "none",
    )


def _has_recent_backup(ctx: FeatureContext) -> FeatureValue:
    backup = ctx.workload.backup
    missing = []
    if backup is None or backup.latest_restore_point_utc is None:
        missing.append("latest_restore_point_utc")
        value = False
    else:
        age_days = (
            ctx.now - backup.latest_restore_point_utc.astimezone(timezone.utc)
        ).total_seconds() / 86400
        value = age_days <= ctx.thresholds.recent_backup_days
    return _feature(
        name="has_recent_backup",
        version="1",
        value=value,
        required=("latest_restore_point_utc",),
        missing=missing,
        source_refs=ctx.source_refs("latest_restore_point_utc"),
        trace=f"Latest restore point within {ctx.thresholds.recent_backup_days} days.",
        confidence_impact="lowers_confidence" if missing else "none",
    )


def _stale_backup(ctx: FeatureContext) -> FeatureValue:
    backup = ctx.workload.backup
    missing = []
    if backup is None or backup.latest_restore_point_utc is None:
        missing.append("latest_restore_point_utc")
        value = False
    else:
        age_days = (
            ctx.now - backup.latest_restore_point_utc.astimezone(timezone.utc)
        ).total_seconds() / 86400
        value = age_days > ctx.thresholds.stale_backup_days
    return _feature(
        name="stale_backup",
        version="1",
        value=value,
        required=("latest_restore_point_utc",),
        missing=missing,
        source_refs=ctx.source_refs("latest_restore_point_utc"),
        trace=f"Latest restore point older than {ctx.thresholds.stale_backup_days} days.",
        confidence_impact="lowers_confidence" if missing else "none",
    )


def _last_seen_age_days(ctx: FeatureContext) -> FeatureValue:
    last_seen = ctx.workload.inventory.last_seen
    if last_seen is None:
        value = None
        missing = ["last_seen"]
    else:
        value = (ctx.now - last_seen.astimezone(timezone.utc)).total_seconds() / 86400
        missing = []
    return _feature(
        name="last_seen_age_days",
        version="1",
        value=value,
        required=("last_seen",),
        missing=missing,
        source_refs=ctx.source_refs("last_seen"),
        trace="Days since inventory last saw the workload.",
        confidence_impact="lowers_confidence" if missing else "none",
    )


def _last_powered_on_age_days(ctx: FeatureContext) -> FeatureValue:
    last_powered_on = ctx.workload.inventory.last_powered_on
    if last_powered_on is None:
        value = None
        missing = ["last_powered_on"]
    else:
        value = (ctx.now - last_powered_on.astimezone(timezone.utc)).total_seconds() / 86400
        missing = []
    return _feature(
        name="last_powered_on_age_days",
        version="1",
        value=value,
        required=("last_powered_on",),
        missing=missing,
        source_refs=ctx.source_refs("last_powered_on"),
        trace="Days since the workload was last powered on.",
        confidence_impact="lowers_confidence" if missing else "none",
    )


def _stale_inventory_seen(ctx: FeatureContext) -> FeatureValue:
    age_days = ctx.features["last_seen_age_days"].value
    value = age_days is not None and age_days > ctx.thresholds.stale_backup_days
    missing = [] if age_days is not None else ["last_seen_age_days"]
    return _feature(
        name="stale_inventory_seen",
        version="1",
        value=value,
        required=("last_seen_age_days",),
        missing=missing,
        source_refs=ctx.features["last_seen_age_days"].source_refs,
        trace=f"Inventory last-seen age is greater than {ctx.thresholds.stale_backup_days} days.",
        confidence_impact="lowers_confidence" if missing else "none",
    )


def _rpo_hours(ctx: FeatureContext) -> FeatureValue:
    backup = ctx.workload.backup
    value = backup.rpo_hours if backup else None
    missing = [] if value is not None else ["rpo_hours"]
    return _feature(
        name="rpo_hours",
        version="1",
        value=value,
        required=("rpo_hours",),
        missing=missing,
        source_refs=ctx.source_refs("rpo_hours"),
        trace="RPO hours supplied by backup metadata.",
        confidence_impact="lowers_confidence" if missing else "none",
    )


def _long_rpo_review(ctx: FeatureContext) -> FeatureValue:
    rpo = ctx.features["rpo_hours"].value
    value = rpo is not None and rpo > 24
    missing = [] if rpo is not None else ["rpo_hours"]
    return _feature(
        name="long_rpo_review",
        version="1",
        value=value,
        required=("rpo_hours",),
        missing=missing,
        source_refs=ctx.features["rpo_hours"].source_refs,
        trace="True when RPO is greater than 24 hours and should be reviewed.",
        confidence_impact="lowers_confidence" if missing else "none",
    )


def _power_state_flags(ctx: FeatureContext, name: str) -> FeatureValue:
    state = (ctx.workload.inventory.power_state or "").strip().lower()
    compact_state = state.replace(" ", "")
    off = any(
        token in state or token in compact_state
        for token in (
            "poweredoff",
            "powered off",
            "off",
            "stopped",
            "deallocated",
            "shutdown",
            "apagado",
            "detenido",
            "aus",
            "arrete",
        )
    )
    on = not off and any(
        token in state or token in compact_state
        for token in (
            "poweredon",
            "powered on",
            "running",
            "started",
            "on",
            "encendido",
            "activo",
            "en marche",
        )
    )
    value = on if name == "powered_on" else off
    return _feature(
        name=name,
        version="1",
        value=value,
        required=("power_state",),
        missing=[] if state else ["power_state"],
        source_refs=ctx.source_refs("power_state"),
        trace="Power-state text matched against common on/off terms.",
        confidence_impact="lowers_confidence" if not state else "none",
    )


def _powered_on(ctx: FeatureContext) -> FeatureValue:
    return _power_state_flags(ctx, "powered_on")


def _powered_off(ctx: FeatureContext) -> FeatureValue:
    return _power_state_flags(ctx, "powered_off")


def _high_allocated_cpu(ctx: FeatureContext) -> FeatureValue:
    cpu_count = ctx.workload.inventory.cpu_count
    missing = ["cpu_count"] if cpu_count is None else []
    value = cpu_count is not None and cpu_count >= ctx.thresholds.high_cpu_count
    return _feature(
        name="high_allocated_cpu",
        version="1",
        value=value,
        required=("cpu_count",),
        optional=("cpu_usage_pct",),
        missing=missing,
        source_refs=ctx.source_refs("cpu_count", "cpu_usage_pct"),
        trace=f"CPU allocation is at least {ctx.thresholds.high_cpu_count}.",
        confidence_impact="lowers_confidence" if missing else "none",
    )


def _high_allocated_memory(ctx: FeatureContext) -> FeatureValue:
    memory_mib = ctx.workload.inventory.memory_mib
    missing = ["memory_mib"] if memory_mib is None else []
    value = memory_mib is not None and memory_mib >= ctx.thresholds.high_memory_mib
    return _feature(
        name="high_allocated_memory",
        version="1",
        value=value,
        required=("memory_mib",),
        optional=("memory_usage_pct",),
        missing=missing,
        source_refs=ctx.source_refs("memory_mib", "memory_usage_pct"),
        trace=f"Memory allocation is at least {ctx.thresholds.high_memory_mib} MiB.",
        confidence_impact="lowers_confidence" if missing else "none",
    )


def _large_backup_footprint(ctx: FeatureContext) -> FeatureValue:
    backup = ctx.workload.backup
    missing = ["backup_total_mib"] if backup is None or backup.backup_total_mib is None else []
    value = (
        backup is not None
        and backup.backup_total_mib is not None
        and backup.backup_total_mib >= ctx.thresholds.large_backup_mib
    )
    return _feature(
        name="large_backup_footprint",
        version="1",
        value=value,
        required=("backup_total_mib",),
        missing=missing,
        source_refs=ctx.source_refs("backup_total_mib"),
        trace=f"Backup footprint is at least {ctx.thresholds.large_backup_mib} MiB.",
        confidence_impact="lowers_confidence" if missing else "none",
    )


def _low_change_rate(ctx: FeatureContext) -> FeatureValue:
    change_rate = ctx.features["change_rate_pct"].value
    missing = ["change_rate_pct"] if change_rate is None else []
    value = change_rate is not None and change_rate <= ctx.thresholds.low_change_rate_pct
    return _feature(
        name="low_change_rate",
        version="1",
        value=value,
        required=("change_rate_pct",),
        missing=missing,
        source_refs=ctx.features["change_rate_pct"].source_refs,
        trace=f"Change rate is at or below {ctx.thresholds.low_change_rate_pct} percent.",
        confidence_impact="lowers_confidence" if missing else "none",
    )


def _snapshot_present(ctx: FeatureContext) -> FeatureValue:
    snapshot = ctx.workload.inventory.snapshot_total_mib
    value = snapshot is not None and snapshot > 0
    return _feature(
        name="snapshot_present",
        version="1",
        value=value,
        required=("snapshot_total_mib",),
        missing=[],
        source_refs=ctx.source_refs("snapshot_total_mib"),
        trace="Snapshot total is present and greater than zero.",
    )


def _provisioned_to_used_ratio(ctx: FeatureContext) -> FeatureValue:
    inventory = ctx.workload.inventory
    missing: list[str] = []
    if inventory.provisioned_mib is None or inventory.provisioned_mib <= 0:
        missing.append("provisioned_mib")
    if inventory.in_use_mib is None or inventory.in_use_mib <= 0:
        missing.append("in_use_mib")
    value = None
    if not missing:
        value = inventory.provisioned_mib / inventory.in_use_mib  # type: ignore[operator]
    return _feature(
        name="provisioned_to_used_ratio",
        version="1",
        value=value,
        required=("provisioned_mib", "in_use_mib"),
        missing=missing,
        source_refs=ctx.source_refs("provisioned_mib", "in_use_mib"),
        trace="Provisioned storage divided by in-use storage.",
        confidence_impact="lowers_confidence" if missing else "none",
    )


def _snapshot_to_used_ratio(ctx: FeatureContext) -> FeatureValue:
    inventory = ctx.workload.inventory
    missing: list[str] = []
    if inventory.snapshot_total_mib is None:
        missing.append("snapshot_total_mib")
    if inventory.in_use_mib is None or inventory.in_use_mib <= 0:
        missing.append("in_use_mib")
    value = None
    if not missing:
        value = inventory.snapshot_total_mib / inventory.in_use_mib  # type: ignore[operator]
    return _feature(
        name="snapshot_to_used_ratio",
        version="1",
        value=value,
        required=("snapshot_total_mib", "in_use_mib"),
        missing=missing,
        source_refs=ctx.source_refs("snapshot_total_mib", "in_use_mib"),
        trace="Snapshot footprint divided by in-use storage.",
        confidence_impact="lowers_confidence" if missing else "none",
    )


def _application_context_present(ctx: FeatureContext) -> FeatureValue:
    inventory = ctx.workload.inventory
    fields = {
        "datacenter": inventory.datacenter,
        "cluster": inventory.cluster,
        "host": inventory.host,
        "tags": inventory.tags,
        "notes": inventory.notes,
    }
    present = sorted(field for field, value in fields.items() if value)
    return _feature(
        name="application_context_present",
        version="1",
        value=bool(present),
        optional=tuple(fields),
        source_refs=ctx.source_refs(*fields.keys()),
        trace="True when inventory carries contextual fields such as datacenter, cluster, host, tags, or notes.",
        confidence_impact="none" if present else "lowers_confidence",
    )


def _protection_policy_context_present(ctx: FeatureContext) -> FeatureValue:
    backup = ctx.workload.backup
    fields = {
        "backup_policy": backup.backup_policy if backup else None,
        "retention_days": backup.retention_days if backup else None,
        "rpo_hours": backup.rpo_hours if backup else None,
        "rto_tier": backup.rto_tier if backup else None,
    }
    present = sorted(field for field, value in fields.items() if value is not None)
    return _feature(
        name="protection_policy_context_present",
        version="1",
        value=bool(present),
        optional=tuple(fields),
        source_refs=ctx.source_refs(*fields.keys()),
        trace="True when backup evidence includes policy, retention, RPO, or RTO context.",
        confidence_impact="none" if present else "lowers_confidence",
    )


def _data_quality_finding_count(ctx: FeatureContext) -> FeatureValue:
    findings = [
        *ctx.workload.inventory_record.data_quality,
        *(ctx.workload.backup_record.data_quality if ctx.workload.backup_record else []),
        *ctx.workload.data_quality,
    ]
    return _feature(
        name="data_quality_finding_count",
        version="1",
        value=len(findings),
        trace="Count of structured data-quality findings attached to this workload.",
        confidence_impact="lowers_confidence" if findings else "none",
    )


def _data_quality_risk(ctx: FeatureContext) -> FeatureValue:
    findings = [
        *ctx.workload.inventory_record.data_quality,
        *(ctx.workload.backup_record.data_quality if ctx.workload.backup_record else []),
        *ctx.workload.data_quality,
    ]
    if any(finding.severity == "error" for finding in findings):
        value = "high"
    elif any(finding.severity == "warning" for finding in findings):
        value = "medium"
    else:
        value = "low"
    return _feature(
        name="data_quality_risk",
        version="1",
        value=value,
        trace="Highest data-quality severity attached to this workload.",
        confidence_impact="lowers_confidence" if value != "low" else "none",
    )


def _os_unknown(ctx: FeatureContext) -> FeatureValue:
    os_value = ctx.workload.inventory.os
    value = os_value is None or os_value.strip().lower() in {"", "unknown", "n/a", "na", "none"}
    return _feature(
        name="os_unknown",
        version="1",
        value=value,
        required=("os",),
        missing=["os"] if value else [],
        source_refs=ctx.source_refs("os"),
        trace="OS is missing or marked unknown.",
        confidence_impact="lowers_confidence" if value else "none",
    )


def _util_values(ctx: FeatureContext, field: str) -> list[Any]:
    values: list[Any] = []
    for record in ctx.workload.utilization_records:
        value = record.value(field)
        if value is not None:
            values.append(value)
    return values


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _util_pct_feature(ctx: FeatureContext, name: str) -> FeatureValue:
    values = [value for value in _util_values(ctx, name) if isinstance(value, (int, float))]
    value = max(values) if values else None
    return _feature(
        name=name,
        version="1",
        value=value,
        required=(name,),
        missing=[] if values else [name],
        source_refs=ctx.source_refs(name),
        trace=f"Maximum observed {name} across matched utilization rows.",
        confidence_impact="lowers_confidence" if not values else "none",
    )


def _cpu_p95_pct(ctx: FeatureContext) -> FeatureValue:
    return _util_pct_feature(ctx, "cpu_p95_pct")


def _memory_p95_pct(ctx: FeatureContext) -> FeatureValue:
    return _util_pct_feature(ctx, "memory_p95_pct")


def _utilization_sample_count(ctx: FeatureContext) -> FeatureValue:
    counts = [value for value in _util_values(ctx, "sample_count") if isinstance(value, int)]
    value = sum(counts) if counts else None
    return _feature(
        name="utilization_sample_count",
        version="1",
        value=value,
        required=("sample_count",),
        missing=[] if counts else ["sample_count"],
        source_refs=ctx.source_refs("sample_count"),
        trace="Sum of matched utilization sample counts.",
        confidence_impact="lowers_confidence" if not counts else "none",
    )


def _utilization_window_days(ctx: FeatureContext) -> FeatureValue:
    starts = [
        parsed
        for value in _util_values(ctx, "sample_start_utc")
        if (parsed := _as_datetime(value)) is not None
    ]
    ends = [
        parsed
        for value in _util_values(ctx, "sample_end_utc")
        if (parsed := _as_datetime(value)) is not None
    ]
    if not starts or not ends:
        value = None
        missing = ["sample_start_utc", "sample_end_utc"]
    else:
        value = (max(ends) - min(starts)).total_seconds() / 86400
        missing = []
    return _feature(
        name="utilization_window_days",
        version="1",
        value=value,
        required=("sample_start_utc", "sample_end_utc"),
        missing=missing,
        source_refs=ctx.source_refs("sample_start_utc", "sample_end_utc"),
        trace="Days covered by matched utilization samples.",
        confidence_impact="lowers_confidence" if missing else "none",
    )


def _utilization_sample_quality(ctx: FeatureContext) -> FeatureValue:
    sample_count = ctx.features["utilization_sample_count"].value
    window_days = ctx.features["utilization_window_days"].value
    value = (
        sample_count is not None
        and sample_count >= 24
        and window_days is not None
        and window_days >= 1
    )
    missing: list[str] = []
    if sample_count is None:
        missing.append("sample_count")
    if window_days is None:
        missing.append("utilization_window_days")
    return _feature(
        name="utilization_sample_quality",
        version="1",
        value=value,
        required=("sample_count", "utilization_window_days"),
        missing=missing,
        source_refs=[
            *ctx.features["utilization_sample_count"].source_refs,
            *ctx.features["utilization_window_days"].source_refs,
        ],
        trace="True when utilization has at least 24 samples spanning at least one day.",
        confidence_impact="lowers_confidence" if not value else "none",
    )


FEATURE_REGISTRY: tuple[FeatureCalculator, ...] = (
    FeatureCalculator("workload_key", "1", ("uuid|normalized_name",), (), _workload_key),
    FeatureCalculator("backup_matched", "1", (), (), _backup_matched),
    FeatureCalculator("backup_to_used_ratio", "1", ("backup_total_mib", "in_use_mib"), (), _backup_to_used_ratio),
    FeatureCalculator("change_rate_pct", "1", ("avg_daily_change_mib", "in_use_mib"), (), _change_rate_pct),
    FeatureCalculator("has_recent_backup", "1", ("latest_restore_point_utc",), (), _has_recent_backup),
    FeatureCalculator("stale_backup", "1", ("latest_restore_point_utc",), (), _stale_backup),
    FeatureCalculator("last_seen_age_days", "1", ("last_seen",), (), _last_seen_age_days),
    FeatureCalculator("last_powered_on_age_days", "1", ("last_powered_on",), (), _last_powered_on_age_days),
    FeatureCalculator("stale_inventory_seen", "1", ("last_seen_age_days",), (), _stale_inventory_seen),
    FeatureCalculator("rpo_hours", "1", ("rpo_hours",), (), _rpo_hours),
    FeatureCalculator("long_rpo_review", "1", ("rpo_hours",), (), _long_rpo_review),
    FeatureCalculator("powered_on", "1", ("power_state",), (), _powered_on),
    FeatureCalculator("powered_off", "1", ("power_state",), (), _powered_off),
    FeatureCalculator("high_allocated_cpu", "1", ("cpu_count",), ("cpu_usage_pct",), _high_allocated_cpu),
    FeatureCalculator("high_allocated_memory", "1", ("memory_mib",), ("memory_usage_pct",), _high_allocated_memory),
    FeatureCalculator("large_backup_footprint", "1", ("backup_total_mib",), (), _large_backup_footprint),
    FeatureCalculator("low_change_rate", "1", ("change_rate_pct",), (), _low_change_rate),
    FeatureCalculator("snapshot_present", "1", ("snapshot_total_mib",), (), _snapshot_present),
    FeatureCalculator("provisioned_to_used_ratio", "1", ("provisioned_mib", "in_use_mib"), (), _provisioned_to_used_ratio),
    FeatureCalculator("snapshot_to_used_ratio", "1", ("snapshot_total_mib", "in_use_mib"), (), _snapshot_to_used_ratio),
    FeatureCalculator("application_context_present", "1", (), ("datacenter", "cluster", "host", "tags", "notes"), _application_context_present),
    FeatureCalculator("protection_policy_context_present", "1", (), ("backup_policy", "retention_days", "rpo_hours", "rto_tier"), _protection_policy_context_present),
    FeatureCalculator("data_quality_finding_count", "1", (), (), _data_quality_finding_count),
    FeatureCalculator("data_quality_risk", "1", (), (), _data_quality_risk),
    FeatureCalculator("os_unknown", "1", ("os",), (), _os_unknown),
    FeatureCalculator("cpu_p95_pct", "1", ("cpu_p95_pct",), (), _cpu_p95_pct),
    FeatureCalculator("memory_p95_pct", "1", ("memory_p95_pct",), (), _memory_p95_pct),
    FeatureCalculator("utilization_sample_count", "1", ("sample_count",), (), _utilization_sample_count),
    FeatureCalculator("utilization_window_days", "1", ("sample_start_utc", "sample_end_utc"), (), _utilization_window_days),
    FeatureCalculator("utilization_sample_quality", "1", ("sample_count", "utilization_window_days"), (), _utilization_sample_quality),
)


def compute_features(
    workload: ResolvedWorkload,
    thresholds: Thresholds,
    *,
    now: datetime | None = None,
) -> FeatureSet:
    features: dict[str, FeatureValue] = {}
    for calculator in FEATURE_REGISTRY:
        context = FeatureContext(workload, thresholds, now=now, features=features)
        features[calculator.name] = calculator.compute(context)

    missing: list[str] = []
    optional_utilization_features = {
        "cpu_p95_pct",
        "memory_p95_pct",
        "utilization_sample_count",
        "utilization_window_days",
        "utilization_sample_quality",
    }
    optional_recency_features = {
        "last_seen_age_days",
        "last_powered_on_age_days",
        "stale_inventory_seen",
    }
    for feature in features.values():
        if feature.name in optional_utilization_features and not workload.utilization_records:
            continue
        if feature.name in optional_recency_features:
            continue
        for missing_field in feature.missing_evidence:
            if missing_field not in missing:
                missing.append(missing_field)

    inventory = workload.inventory
    has_cpu_util = inventory.cpu_usage_pct is not None or features["cpu_p95_pct"].value is not None
    has_memory_util = (
        inventory.memory_usage_pct is not None or features["memory_p95_pct"].value is not None
    )
    if features["high_allocated_cpu"].value and not has_cpu_util and "cpu_usage_pct" not in missing:
        missing.append("cpu_usage_pct")
    if (
        features["high_allocated_memory"].value
        and not has_memory_util
        and "memory_usage_pct" not in missing
    ):
        missing.append("memory_usage_pct")
    if workload.backup is None:
        for field in ("backup_total_mib", "avg_daily_change_mib", "restore_point_count"):
            if field not in missing:
                missing.append(field)
    elif workload.backup.restore_point_count is None and "restore_point_count" not in missing:
        missing.append("restore_point_count")

    return FeatureSet(
        workload_id=workload.workload_id,
        features=features,
        missing_evidence=missing,
        confidence_summary=dict(Counter(feature.confidence_impact for feature in features.values())),
    )


def to_derived_features(feature_set: FeatureSet) -> DerivedFeatures:
    return DerivedFeatures(
        workload_key=feature_set.value("workload_key"),
        backup_to_used_ratio=feature_set.value("backup_to_used_ratio"),
        change_rate_pct=feature_set.value("change_rate_pct"),
        has_recent_backup=feature_set.value("has_recent_backup") or False,
        stale_backup=feature_set.value("stale_backup") or False,
        powered_on=feature_set.value("powered_on") or False,
        powered_off=feature_set.value("powered_off") or False,
        high_allocated_cpu=feature_set.value("high_allocated_cpu") or False,
        high_allocated_memory=feature_set.value("high_allocated_memory") or False,
        large_backup_footprint=feature_set.value("large_backup_footprint") or False,
        low_change_rate=feature_set.value("low_change_rate") or False,
        snapshot_present=feature_set.value("snapshot_present") or False,
        missing_data=feature_set.missing_evidence,
    )
