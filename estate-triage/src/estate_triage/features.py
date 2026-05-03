"""Feature derivation from joined workload records."""

from __future__ import annotations

from datetime import datetime, timezone

from estate_triage.config import Thresholds
from estate_triage.models import DerivedFeatures, JoinedWorkload


def _add_missing(missing: list[str], field: str) -> None:
    if field not in missing:
        missing.append(field)


def _is_unknown_os(value: str | None) -> bool:
    if value is None:
        return True
    return value.strip().lower() in {"", "unknown", "n/a", "na", "none"}


def is_unknown_os(value: str | None) -> bool:
    return _is_unknown_os(value)


def derive_features(
    joined: JoinedWorkload,
    thresholds: Thresholds,
    *,
    now: datetime | None = None,
) -> DerivedFeatures:
    inventory = joined.inventory
    backup = joined.backup
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    missing: list[str] = []

    workload_key = inventory.uuid or inventory.normalized_name

    backup_total_mib = backup.backup_total_mib if backup else None
    in_use_mib = inventory.in_use_mib
    avg_daily_change_mib = backup.avg_daily_change_mib if backup else None

    if in_use_mib is None or in_use_mib <= 0:
        _add_missing(missing, "in_use_mib")
        backup_to_used_ratio = None
        change_rate_pct = None
    else:
        if backup_total_mib is None:
            _add_missing(missing, "backup_total_mib")
            backup_to_used_ratio = None
        else:
            backup_to_used_ratio = backup_total_mib / in_use_mib

        if avg_daily_change_mib is None or avg_daily_change_mib <= 0:
            _add_missing(missing, "avg_daily_change_mib")
            change_rate_pct = None
        else:
            change_rate_pct = (avg_daily_change_mib / in_use_mib) * 100

    latest_restore = backup.latest_restore_point_utc if backup else None
    if latest_restore is None:
        _add_missing(missing, "latest_restore_point_utc")
        has_recent_backup = False
        stale_backup = False
    else:
        age_days = (now_utc - latest_restore.astimezone(timezone.utc)).total_seconds() / 86400
        has_recent_backup = age_days <= thresholds.recent_backup_days
        stale_backup = age_days > thresholds.stale_backup_days

    if backup is None:
        _add_missing(missing, "backup_total_mib")
        _add_missing(missing, "avg_daily_change_mib")
        _add_missing(missing, "restore_point_count")
    elif backup.restore_point_count is None:
        _add_missing(missing, "restore_point_count")

    if _is_unknown_os(inventory.os):
        _add_missing(missing, "os")

    state = (inventory.power_state or "").strip().lower()
    compact_state = state.replace(" ", "")
    powered_off = any(
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
    powered_on = not powered_off and any(
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
    if not state:
        _add_missing(missing, "power_state")

    high_allocated_cpu = (
        inventory.cpu_count is not None and inventory.cpu_count >= thresholds.high_cpu_count
    )
    high_allocated_memory = (
        inventory.memory_mib is not None and inventory.memory_mib >= thresholds.high_memory_mib
    )
    if high_allocated_cpu and inventory.cpu_usage_pct is None:
        _add_missing(missing, "cpu_usage_pct")
    if high_allocated_memory and inventory.memory_usage_pct is None:
        _add_missing(missing, "memory_usage_pct")

    return DerivedFeatures(
        workload_key=workload_key,
        backup_to_used_ratio=backup_to_used_ratio,
        change_rate_pct=change_rate_pct,
        has_recent_backup=has_recent_backup,
        stale_backup=stale_backup,
        powered_on=powered_on,
        powered_off=powered_off,
        high_allocated_cpu=high_allocated_cpu,
        high_allocated_memory=high_allocated_memory,
        large_backup_footprint=(
            backup_total_mib is not None and backup_total_mib >= thresholds.large_backup_mib
        ),
        low_change_rate=(
            change_rate_pct is not None and change_rate_pct <= thresholds.low_change_rate_pct
        ),
        snapshot_present=(
            inventory.snapshot_total_mib is not None and inventory.snapshot_total_mib > 0
        ),
        missing_data=missing,
    )
