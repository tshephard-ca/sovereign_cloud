from datetime import datetime, timezone

from estate_triage.config import Thresholds
from estate_triage.features import derive_features
from estate_triage.models import BackupMetadata, JoinedWorkload, WorkloadInventory


NOW = datetime(2026, 4, 30, tzinfo=timezone.utc)


def test_change_rate_and_backup_ratio_are_derived():
    joined = JoinedWorkload(
        inventory=WorkloadInventory(
            source_row=2,
            name="app",
            normalized_name="app",
            uuid="uuid-a",
            in_use_mib=100000,
        ),
        backup=BackupMetadata(
            source_row=2,
            name="app",
            normalized_name="app",
            uuid="uuid-a",
            backup_total_mib=300000,
            avg_daily_change_mib=500,
            latest_restore_point_utc=NOW,
            restore_point_count=10,
        ),
        matched_by="UUID",
    )

    features = derive_features(joined, Thresholds(), now=NOW)

    assert features.backup_to_used_ratio == 3
    assert features.change_rate_pct == 0.5
    assert features.low_change_rate is True
    assert features.has_recent_backup is True


def test_missing_storage_used_prevents_ratio_calculation():
    joined = JoinedWorkload(
        inventory=WorkloadInventory(
            source_row=2,
            name="app",
            normalized_name="app",
            uuid="uuid-a",
            in_use_mib=None,
        ),
        backup=BackupMetadata(
            source_row=2,
            name="app",
            normalized_name="app",
            uuid="uuid-a",
            backup_total_mib=300000,
            avg_daily_change_mib=500,
            latest_restore_point_utc=NOW,
        ),
        matched_by="UUID",
    )

    features = derive_features(joined, Thresholds(), now=NOW)

    assert features.backup_to_used_ratio is None
    assert features.change_rate_pct is None
    assert "in_use_mib" in features.missing_data
