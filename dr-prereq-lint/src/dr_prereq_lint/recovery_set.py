"""Recovery-set selection and matching helpers."""

from __future__ import annotations

from .models import BackupInventoryRow, ProtectedSystem, RecoverySet


ROLE_TAGS_BY_CATEGORY: dict[str, set[str]] = {
    "directory_service": {"domain_controller", "directory_service", "active_directory", "global_catalog", "kerberos", "kdc"},
    "kerberos_service": {"domain_controller", "directory_service", "active_directory", "kerberos", "kdc"},
    "global_catalog": {"domain_controller", "directory_service", "active_directory", "global_catalog"},
}


def build_recovery_set(
    rows: list[BackupInventoryRow],
    *,
    recovery_set_name: str | None = None,
    strict: bool = False,
) -> RecoverySet:
    warnings: list[str] = []
    systems: list[ProtectedSystem] = []
    any_include_column_values = any(row.include_in_recovery_set is not None for row in rows)
    any_recovery_set_values = any(row.recovery_set for row in rows)
    if strict and not any_include_column_values:
        raise ValueError("recovery-set membership cannot be determined without include_in_recovery_set-like data")
    if strict and recovery_set_name and not any_recovery_set_values:
        raise ValueError("recovery-set membership cannot be determined without recovery_set-like data")

    for row in rows:
        if not row.protected:
            continue
        if recovery_set_name and row.recovery_set and row.recovery_set != recovery_set_name:
            continue
        if recovery_set_name and not row.recovery_set:
            continue
        include = row.include_in_recovery_set
        if include is None:
            include = row.protected
            if "RECOVERY_SET_SCOPE_ASSUMED" not in warnings:
                warnings.append("RECOVERY_SET_SCOPE_ASSUMED")
        if include:
            systems.append(
                ProtectedSystem(
                    source_row=row.source_row,
                    workload_name=row.workload_name,
                    fqdn=row.fqdn,
                    short_name=row.short_name,
                    ip_addresses=row.ip_addresses,
                    recovery_set=row.recovery_set,
                    include_in_recovery_set=row.include_in_recovery_set,
                    aliases=row.aliases,
                    role_tags=row.role_tags,
                )
            )
    return RecoverySet(name=recovery_set_name or "", systems=systems, warnings=warnings)


def system_display_name(system: ProtectedSystem) -> str:
    return system.fqdn or system.workload_name or system.short_name or f"inventory:{system.source_row}"


def role_tag_present(recovery_set: RecoverySet, category: str) -> bool:
    expected = ROLE_TAGS_BY_CATEGORY.get(category, set())
    return any(expected.intersection(set(system.role_tags)) for system in recovery_set.systems)
