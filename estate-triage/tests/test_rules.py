from datetime import datetime, timezone

from estate_triage.config import Thresholds
from estate_triage.models import BackupMetadata, JoinedWorkload, WorkloadInventory
from estate_triage.scoring import score_joined_workload


NOW = datetime(2026, 4, 30, tzinfo=timezone.utc)


def workload(**overrides) -> WorkloadInventory:
    values = {
        "source_row": 2,
        "name": "workload",
        "normalized_name": "workload",
        "uuid": "uuid-a",
        "power_state": "poweredOn",
        "cpu_count": 2,
        "memory_mib": 4096,
        "in_use_mib": 100000,
        "os": "Generic Linux",
        "snapshot_total_mib": 0,
    }
    values.update(overrides)
    return WorkloadInventory(**values)


def backup(**overrides) -> BackupMetadata:
    values = {
        "source_row": 2,
        "name": "workload",
        "normalized_name": "workload",
        "uuid": "uuid-a",
        "backup_total_mib": 120000,
        "avg_daily_change_mib": 500,
        "latest_restore_point_utc": NOW,
        "restore_point_count": 14,
    }
    values.update(overrides)
    return BackupMetadata(**values)


def result_for(inv: WorkloadInventory, bak: BackupMetadata | None, matched_by="UUID"):
    return score_joined_workload(
        JoinedWorkload(inventory=inv, backup=bak, matched_by=matched_by),
        Thresholds(),
        now=NOW,
    )


def test_low_change_large_backup_dr_candidate():
    result = result_for(
        workload(in_use_mib=400000),
        backup(backup_total_mib=1600000, avg_daily_change_mib=1000, restore_point_count=40),
    )

    assert result.primary_motion == "DR_TIER_REVIEW"
    assert "LOW_CHANGE_RATE" in result.reason_codes
    assert "LARGE_BACKUP_FOOTPRINT" in result.reason_codes
    assert "DR tier review candidate" in result.reason_text


def test_powered_off_archive_review_candidate():
    stale = datetime(2025, 12, 1, tzinfo=timezone.utc)
    result = result_for(
        workload(power_state="poweredOff", os="Unknown", in_use_mib=50000),
        backup(latest_restore_point_utc=stale),
    )

    assert result.primary_motion == "ARCHIVE_REVIEW"
    assert "POWERED_OFF" in result.reason_codes
    assert "STALE_BACKUP" in result.reason_codes
    assert "archive review candidate" in result.reason_text


def test_unmatched_inventory_gets_no_backup_match_flag():
    result = result_for(workload(), None, matched_by="NONE")

    assert "NO_BACKUP_MATCH" in result.reason_codes
    assert "NO_BACKUP_MATCH" in result.blocking_flags
    assert result.confidence == "low"


def test_allocation_only_rightsizing_uses_review_language_and_low_confidence():
    result = result_for(
        workload(
            power_state=None,
            cpu_count=16,
            memory_mib=65536,
            in_use_mib=500000,
            cpu_usage_pct=None,
            memory_usage_pct=None,
        ),
        None,
        matched_by="NONE",
    )

    assert result.primary_motion == "RIGHTSIZING_REVIEW"
    assert "HIGH_ALLOCATED_CPU_REVIEW" in result.reason_codes
    assert "HIGH_ALLOCATED_MEMORY_REVIEW" in result.reason_codes
    assert "LOW_CONFIDENCE_RIGHTSIZING" in result.blocking_flags
    assert "needs validation" in result.reason_text
    assert result.confidence == "low"


def test_utilization_backed_rightsizing_uses_utilization_reason_codes():
    stale = datetime(2025, 12, 1, tzinfo=timezone.utc)
    result = result_for(
        workload(
            power_state=None,
            cpu_count=8,
            memory_mib=32768,
            in_use_mib=500000,
            cpu_usage_pct=3,
            memory_usage_pct=22,
        ),
        backup(latest_restore_point_utc=stale, avg_daily_change_mib=None),
    )

    assert result.primary_motion == "RIGHTSIZING_REVIEW"
    assert "IDLE_CPU" in result.reason_codes
    assert "OVERSIZED_MEMORY" in result.reason_codes
    assert result.confidence == "high"


def test_snapshot_present_adds_blocking_flag():
    result = result_for(
        workload(snapshot_total_mib=1024),
        backup(),
    )

    assert "SNAPSHOT_PRESENT" in result.blocking_flags
