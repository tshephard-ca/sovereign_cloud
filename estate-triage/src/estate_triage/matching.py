"""Inventory-to-backup matching."""

from __future__ import annotations

from estate_triage.models import BackupMetadata, JoinedWorkload, WorkloadInventory


def _add_first(
    lookup: dict[str, BackupMetadata],
    key: str | None,
    backup: BackupMetadata,
    *,
    key_name: str,
    warnings: list[str],
) -> None:
    if not key:
        return
    if key in lookup:
        warnings.append(
            f"Backup row {backup.source_row}: duplicate {key_name} {key!r}; first row kept for matching."
        )
        return
    lookup[key] = backup


def join_inventory_to_backup(
    inventory: list[WorkloadInventory],
    backups: list[BackupMetadata],
    *,
    warnings: list[str],
) -> list[JoinedWorkload]:
    by_uuid: dict[str, BackupMetadata] = {}
    by_name: dict[str, BackupMetadata] = {}
    for backup in backups:
        _add_first(by_uuid, backup.uuid, backup, key_name="UUID", warnings=warnings)
        _add_first(by_name, backup.normalized_name, backup, key_name="name", warnings=warnings)

    joined: list[JoinedWorkload] = []
    for workload in inventory:
        row_warnings: list[str] = []
        uuid_match = by_uuid.get(workload.uuid or "")
        name_match = by_name.get(workload.normalized_name)

        if uuid_match is not None:
            if name_match is not None and name_match.source_row != uuid_match.source_row:
                message = (
                    f"Inventory row {workload.source_row}: UUID match uses backup row "
                    f"{uuid_match.source_row}, but name match points to backup row {name_match.source_row}."
                )
                warnings.append(message)
                row_warnings.append(message)
            joined.append(
                JoinedWorkload(
                    inventory=workload,
                    backup=uuid_match,
                    matched_by="UUID",
                    warnings=row_warnings,
                )
            )
        elif name_match is not None:
            joined.append(
                JoinedWorkload(
                    inventory=workload,
                    backup=name_match,
                    matched_by="NAME",
                    warnings=row_warnings,
                )
            )
        else:
            joined.append(
                JoinedWorkload(
                    inventory=workload,
                    backup=None,
                    matched_by="NONE",
                    warnings=row_warnings,
                )
            )
    return joined
