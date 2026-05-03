from estate_triage.matching import join_inventory_to_backup
from estate_triage.models import BackupMetadata, WorkloadInventory


def inv(row: int, name: str, uuid: str | None = None) -> WorkloadInventory:
    return WorkloadInventory(
        source_row=row,
        name=name,
        normalized_name=name.lower(),
        uuid=uuid,
    )


def backup(row: int, name: str, uuid: str | None = None) -> BackupMetadata:
    return BackupMetadata(
        source_row=row,
        name=name,
        normalized_name=name.lower(),
        uuid=uuid,
        backup_total_mib=100,
    )


def test_uuid_match_beats_name_match_when_they_disagree():
    warnings: list[str] = []
    joined = join_inventory_to_backup(
        [inv(2, "shared-name", "uuid-a")],
        [
            backup(2, "shared-name", "uuid-b"),
            backup(3, "other-name", "uuid-a"),
        ],
        warnings=warnings,
    )

    assert joined[0].matched_by == "UUID"
    assert joined[0].backup is not None
    assert joined[0].backup.source_row == 3
    assert warnings


def test_name_match_works_when_uuid_is_absent():
    warnings: list[str] = []
    joined = join_inventory_to_backup(
        [inv(2, "name-only")],
        [backup(2, "name-only")],
        warnings=warnings,
    )

    assert joined[0].matched_by == "NAME"


def test_unmatched_backup_rows_do_not_crash_matching():
    warnings: list[str] = []
    joined = join_inventory_to_backup(
        [inv(2, "inventory-only", "uuid-a")],
        [backup(2, "backup-only", "uuid-b")],
        warnings=warnings,
    )

    assert len(joined) == 1
    assert joined[0].matched_by == "NONE"
