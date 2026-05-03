"""Result assembly and ranking."""

from __future__ import annotations

from datetime import datetime

from estate_triage.config import Thresholds
from estate_triage.features import derive_features
from estate_triage.models import Confidence, JoinedWorkload, MotionScore, TriageResult
from estate_triage.rules import score_all_motions


MOTION_ORDER = {
    "MIGRATION_REVIEW": 0,
    "ARCHIVE_REVIEW": 1,
    "RIGHTSIZING_REVIEW": 2,
    "DR_TIER_REVIEW": 3,
}


def _choose_winner(scores: list[MotionScore]) -> MotionScore:
    return sorted(scores, key=lambda score: (-score.score, MOTION_ORDER[score.motion]))[0]


def _blocking_flags(
    joined: JoinedWorkload,
    features,
    winner: MotionScore,
) -> list[str]:
    flags: list[str] = []

    def add(flag: str) -> None:
        if flag not in flags:
            flags.append(flag)

    if joined.backup is None:
        add("NO_BACKUP_MATCH")
    if features.snapshot_present:
        add("SNAPSHOT_PRESENT")
    if joined.inventory.in_use_mib is None or joined.inventory.in_use_mib <= 0:
        add("MISSING_STORAGE_USED")
    if joined.backup is None or joined.backup.backup_total_mib is None:
        add("MISSING_BACKUP_SIZE")
    if features.change_rate_pct is None:
        add("MISSING_CHANGE_RATE")
    if joined.matched_by == "NAME":
        add("NAME_MATCH_ONLY")
    if winner.motion == "RIGHTSIZING_REVIEW" and winner.allocation_only_rightsizing:
        add("LOW_CONFIDENCE_RIGHTSIZING")
    if features.powered_off:
        add("POWERED_OFF_NOT_MIGRATION_CANDIDATE")
    return flags


def _has_enough_metrics(joined: JoinedWorkload, features, winner: MotionScore) -> bool:
    if winner.motion == "MIGRATION_REVIEW":
        return (
            joined.backup is not None
            and features.has_recent_backup
            and features.change_rate_pct is not None
            and joined.inventory.in_use_mib is not None
            and joined.inventory.os is not None
        )
    if winner.motion == "ARCHIVE_REVIEW":
        return joined.inventory.power_state is not None or features.stale_backup
    if winner.motion == "RIGHTSIZING_REVIEW":
        if winner.allocation_only_rightsizing:
            return False
        return (
            joined.inventory.cpu_usage_pct is not None
            or joined.inventory.memory_usage_pct is not None
        )
    if winner.motion == "DR_TIER_REVIEW":
        return (
            joined.backup is not None
            and joined.backup.backup_total_mib is not None
            and joined.inventory.in_use_mib is not None
            and features.change_rate_pct is not None
        )
    return False


def _confidence(joined: JoinedWorkload, features, winner: MotionScore) -> Confidence:
    if joined.backup is None:
        return "low"
    if winner.motion == "RIGHTSIZING_REVIEW" and winner.allocation_only_rightsizing:
        return "low"
    if not _has_enough_metrics(joined, features, winner):
        return "low"
    if joined.matched_by == "UUID":
        return "high"
    if joined.matched_by == "NAME":
        return "medium"
    return "low"


def score_joined_workload(
    joined: JoinedWorkload,
    thresholds: Thresholds,
    *,
    now: datetime | None = None,
) -> TriageResult:
    features = derive_features(joined, thresholds, now=now)
    scores = score_all_motions(joined, features, thresholds)
    winner = _choose_winner(scores)
    backup = joined.backup
    inventory = joined.inventory

    return TriageResult(
        workload_key=features.workload_key,
        workload_name=inventory.name,
        matched_by=joined.matched_by,
        primary_motion=winner.motion,
        opportunity_score=winner.score,
        confidence=_confidence(joined, features, winner),
        reason_codes=winner.reason_codes,
        reason_text="; ".join(winner.reason_text),
        blocking_flags=_blocking_flags(joined, features, winner),
        missing_data=features.missing_data,
        power_state=inventory.power_state,
        cpu_count=inventory.cpu_count,
        memory_mib=inventory.memory_mib,
        provisioned_mib=inventory.provisioned_mib,
        in_use_mib=inventory.in_use_mib,
        os=inventory.os,
        latest_restore_point_utc=backup.latest_restore_point_utc if backup else None,
        restore_point_count=backup.restore_point_count if backup else None,
        backup_total_mib=backup.backup_total_mib if backup else None,
        avg_daily_change_mib=backup.avg_daily_change_mib if backup else None,
        change_rate_pct=features.change_rate_pct,
        backup_to_used_ratio=features.backup_to_used_ratio,
        source_inventory_row=inventory.source_row,
        source_backup_row=backup.source_row if backup else None,
    )


def rank_results(results: list[TriageResult], *, top_n: int) -> list[TriageResult]:
    ranked = sorted(
        results,
        key=lambda result: (
            -result.opportunity_score,
            MOTION_ORDER[result.primary_motion],
            result.workload_key,
            result.source_inventory_row,
        ),
    )[:top_n]
    for rank, result in enumerate(ranked, start=1):
        result.rank = rank
    return ranked
