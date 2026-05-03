"""Deterministic scoring rules for each sales-engineering motion."""

from __future__ import annotations

from estate_triage.config import Thresholds
from estate_triage.features import is_unknown_os
from estate_triage.models import DerivedFeatures, JoinedWorkload, MotionScore, PrimaryMotion


def _clamp(score: int) -> int:
    return max(0, min(100, score))


def _score(
    motion: PrimaryMotion,
    score: int,
    reason_codes: list[str],
    reason_text: list[str],
    *,
    allocation_only_rightsizing: bool = False,
) -> MotionScore:
    return MotionScore(
        motion=motion,
        score=_clamp(score),
        reason_codes=reason_codes,
        reason_text=reason_text,
        allocation_only_rightsizing=allocation_only_rightsizing,
    )


def score_migration_review(
    joined: JoinedWorkload,
    features: DerivedFeatures,
    thresholds: Thresholds,
) -> MotionScore:
    inventory = joined.inventory
    score = 0
    reasons = ["MIGRATION_REVIEW"]
    text = ["migration review candidate"]

    if features.powered_on:
        score += 20
        text.append("powered on")
    if features.has_recent_backup:
        score += 20
        reasons.append("RECENT_BACKUP")
        text.append("recent restore point")
    if features.low_change_rate:
        score += 20
        reasons.append("LOW_CHANGE_RATE")
        text.append("low daily change rate")
    if inventory.in_use_mib is not None and inventory.in_use_mib < thresholds.small_workload_mib:
        score += 15
        reasons.append("SMALL_STORAGE_FOOTPRINT")
        text.append("small storage footprint")
    if not is_unknown_os(inventory.os):
        score += 10
        text.append("OS present")
    if not features.snapshot_present:
        score += 10
        text.append("no snapshot risk detected")
    if features.snapshot_present:
        score -= 25
        reasons.append("SNAPSHOT_PRESENT")
        text.append("snapshot present")
    if joined.backup is None:
        score -= 20
        reasons.append("NO_BACKUP_MATCH")
        text.append("no backup match")

    return _score("MIGRATION_REVIEW", score, reasons, text)


def score_archive_review(
    joined: JoinedWorkload,
    features: DerivedFeatures,
    thresholds: Thresholds,
) -> MotionScore:
    inventory = joined.inventory
    score = 0
    reasons = ["ARCHIVE_REVIEW"]
    text = ["archive review candidate"]

    if features.powered_off:
        score += 35
        reasons.append("POWERED_OFF")
        text.append("powered off")
    if features.stale_backup:
        score += 20
        reasons.append("STALE_BACKUP")
        text.append("stale restore point")
    if inventory.in_use_mib is not None and inventory.in_use_mib < thresholds.small_workload_mib:
        score += 15
        text.append("small storage footprint")
    if joined.backup is None:
        score += 15
        reasons.append("NO_BACKUP_MATCH")
        text.append("no backup match")
    if is_unknown_os(inventory.os):
        score += 10
        reasons.append("UNKNOWN_OS")
        text.append("OS missing or unknown")
    if features.powered_on:
        score -= 25
        text.append("powered on")

    return _score("ARCHIVE_REVIEW", score, reasons, text)


def score_rightsizing_review(
    joined: JoinedWorkload,
    features: DerivedFeatures,
    thresholds: Thresholds,
) -> MotionScore:
    inventory = joined.inventory
    score = 0
    reasons = ["RIGHTSIZING_REVIEW"]
    text = ["allocation right-sizing review candidate"]

    utilization_backed = False
    allocation_only = False

    if (
        inventory.cpu_usage_pct is not None
        and inventory.cpu_count is not None
        and inventory.cpu_count >= 4
        and inventory.cpu_usage_pct <= thresholds.idle_cpu_pct
    ):
        score += 30
        reasons.append("IDLE_CPU")
        text.append("low CPU utilization with notable allocation")
        utilization_backed = True
    elif inventory.cpu_usage_pct is None and features.high_allocated_cpu:
        score += 20
        reasons.append("HIGH_ALLOCATED_CPU_REVIEW")
        text.append("high allocated CPU needs validation")
        allocation_only = True

    if (
        inventory.memory_usage_pct is not None
        and inventory.memory_mib is not None
        and inventory.memory_mib >= 16384
        and inventory.memory_usage_pct <= thresholds.low_memory_usage_pct
    ):
        score += 30
        reasons.append("OVERSIZED_MEMORY")
        text.append("low memory utilization with notable allocation")
        utilization_backed = True
    elif inventory.memory_usage_pct is None and features.high_allocated_memory:
        score += 20
        reasons.append("HIGH_ALLOCATED_MEMORY_REVIEW")
        text.append("high allocated memory needs validation")
        allocation_only = True

    if features.low_change_rate:
        score += 10
        reasons.append("LOW_CHANGE_RATE")
        text.append("low daily change rate")

    return _score(
        "RIGHTSIZING_REVIEW",
        score,
        reasons,
        text,
        allocation_only_rightsizing=allocation_only and not utilization_backed,
    )


def score_dr_tier_review(
    joined: JoinedWorkload,
    features: DerivedFeatures,
    thresholds: Thresholds,
) -> MotionScore:
    backup = joined.backup
    score = 0
    reasons = ["DR_TIER_REVIEW"]
    text = ["DR tier review candidate"]

    if features.low_change_rate:
        score += 30
        reasons.append("LOW_CHANGE_RATE")
        text.append("low daily change rate")
    if features.large_backup_footprint:
        score += 25
        reasons.append("LARGE_BACKUP_FOOTPRINT")
        text.append("large backup footprint")
    if (
        features.backup_to_used_ratio is not None
        and features.backup_to_used_ratio >= thresholds.high_backup_to_used_ratio
    ):
        score += 15
        reasons.append("HIGH_BACKUP_TO_USED_RATIO")
        text.append("high backup-to-used ratio")
    if backup is not None and backup.restore_point_count is not None:
        if backup.restore_point_count >= thresholds.many_restore_points:
            score += 10
            reasons.append("MANY_RESTORE_POINTS")
            text.append("many restore points")
    if features.has_recent_backup:
        score += 10
        text.append("recent restore point")
    if backup is None:
        score -= 25
        reasons.append("NO_BACKUP_MATCH")
        text.append("no backup match")

    return _score("DR_TIER_REVIEW", score, reasons, text)


def score_all_motions(
    joined: JoinedWorkload,
    features: DerivedFeatures,
    thresholds: Thresholds,
) -> list[MotionScore]:
    return [
        score_migration_review(joined, features, thresholds),
        score_archive_review(joined, features, thresholds),
        score_rightsizing_review(joined, features, thresholds),
        score_dr_tier_review(joined, features, thresholds),
    ]
