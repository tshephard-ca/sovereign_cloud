"""Column alias handling for supported CSV inputs."""

from __future__ import annotations

import re
from collections.abc import Iterable


def column_key(label: str) -> str:
    """Return a stable, forgiving key for comparing CSV headers."""
    return re.sub(r"[^a-z0-9]+", "", label.strip().lower())


INVENTORY_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("VM", "Name", "vm", "vm_name", "workload_name", "Nombre", "Nom"),
    "uuid": ("VM UUID", "UUID", "Instance UUID", "instance_uuid", "bios_uuid", "Identificador", "ID VM"),
    "power_state": ("Powerstate", "Power State", "power_state", "Estado", "Etat", "Statut"),
    "cpu_count": ("CPUs", "vCPUs", "cpu_count", "CPUs asignadas", "Processeurs"),
    "memory_mib": ("Memory", "Memory MiB", "memory_mib", "ram_mib", "Memoria MiB", "Memoire MiB"),
    "provisioned_mib": (
        "Provisioned MiB",
        "provisioned_mib",
        "provisioned_storage_mib",
    ),
    "in_use_mib": ("In use MiB", "In Use MiB", "used_mib", "storage_used_mib", "Usado MiB", "Utilise MiB"),
    "os": ("OS according to the configuration file", "OS", "guest_os", "SO", "Sistema Operativo"),
    "datacenter": ("Datacenter", "datacenter"),
    "cluster": ("Cluster", "cluster"),
    "host": ("Host", "host"),
    "snapshot_total_mib": (
        "Snapshot total MiB",
        "snapshot_total_mib",
        "snapshot_mib",
        "snapshots_mib",
    ),
    "tools_status": ("Tools status", "tools_status"),
    "cpu_usage_pct": ("CPU usage percent", "cpu_usage_pct", "cpu_usage_percent"),
    "memory_usage_pct": (
        "Memory usage percent",
        "memory_usage_pct",
        "memory_usage_percent",
    ),
    "last_powered_on": ("Last powered on date", "last_powered_on", "last_powered_on_date"),
    "last_seen": ("Last seen date", "last_seen", "last_seen_date"),
    "tags": ("Tags", "tags"),
    "notes": ("Notes", "notes"),
}


BACKUP_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("VM", "Name", "vm", "vm_name", "workload_name", "Nombre", "Nom"),
    "uuid": ("VM UUID", "UUID", "Instance UUID", "instance_uuid", "bios_uuid", "Identificador", "ID VM"),
    "backup_total_mib": ("backup_total_mib", "Backup Total MiB", "backup_total", "Total Respaldo MiB"),
    "latest_full_mib": ("latest_full_mib", "Latest Full MiB", "latest_full"),
    "total_backup_mib": ("total_backup_mib", "Total Backup MiB", "total_backup"),
    "latest_restore_point_utc": (
        "latest_restore_point_utc",
        "Latest Restore Point UTC",
    ),
    "restore_point_count": ("restore_point_count", "Restore Point Count"),
    "avg_daily_change_mib": ("avg_daily_change_mib", "Average Daily Change MiB"),
    "latest_incremental_mib": ("latest_incremental_mib", "Latest Incremental MiB"),
    "backup_job": ("backup_job", "Backup Job"),
    "backup_policy": ("backup_policy", "Backup Policy"),
    "retention_days": ("retention_days", "Retention Days"),
    "immutable_until_utc": ("immutable_until_utc", "Immutable Until UTC"),
    "rpo_hours": ("rpo_hours", "RPO Hours"),
    "rto_tier": ("rto_tier", "RTO Tier"),
    "repository": ("repository", "Repository"),
    "protected": ("protected", "Protected"),
    "last_success_utc": ("last_success_utc", "Last Success UTC"),
    "last_failure_utc": ("last_failure_utc", "Last Failure UTC"),
}


UTILIZATION_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("VM", "Name", "vm", "vm_name", "workload_name", "Nombre", "Nom"),
    "uuid": ("VM UUID", "UUID", "Instance UUID", "instance_uuid", "bios_uuid", "Identificador", "ID VM"),
    "sample_start_utc": ("sample_start_utc", "Sample Start UTC", "start_utc"),
    "sample_end_utc": ("sample_end_utc", "Sample End UTC", "end_utc"),
    "cpu_avg_pct": ("cpu_avg_pct", "CPU Avg Percent", "cpu_average_pct"),
    "cpu_p95_pct": ("cpu_p95_pct", "CPU P95 Percent", "cpu_95th_pct"),
    "cpu_max_pct": ("cpu_max_pct", "CPU Max Percent", "cpu_peak_pct"),
    "memory_avg_pct": ("memory_avg_pct", "Memory Avg Percent", "memory_average_pct"),
    "memory_p95_pct": ("memory_p95_pct", "Memory P95 Percent", "memory_95th_pct"),
    "memory_max_pct": ("memory_max_pct", "Memory Max Percent", "memory_peak_pct"),
    "sample_count": ("sample_count", "Sample Count", "samples"),
}


def build_alias_lookup(aliases: dict[str, Iterable[str]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for canonical, labels in aliases.items():
        lookup[column_key(canonical)] = canonical
        for label in labels:
            lookup[column_key(label)] = canonical
    return lookup


def identify_columns(
    headers: Iterable[str],
    aliases: dict[str, Iterable[str]],
) -> dict[str, str]:
    """Map canonical field names to concrete CSV headers."""
    lookup = build_alias_lookup(aliases)
    identified: dict[str, str] = {}
    for header in headers:
        canonical = lookup.get(column_key(header))
        if canonical and canonical not in identified:
            identified[canonical] = header
    return identified
