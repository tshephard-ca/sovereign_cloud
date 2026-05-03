"""Small versioned policy engine for deterministic triage rules."""

from __future__ import annotations

from typing import Any, Literal
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from estate_triage.config import Thresholds
from estate_triage.evidence import POLICY_SCHEMA_VERSION
from estate_triage.feature_engine import FeatureSet
from estate_triage.identity import ResolvedWorkload
from estate_triage.models import PrimaryMotion
from estate_triage.models import TriageError


ConditionOp = Literal["eq", "ne", "lt", "lte", "gt", "gte", "present", "missing"]


class Condition(BaseModel):
    field: str
    op: ConditionOp
    value: Any = None
    threshold: str | None = None


class ConditionGroup(BaseModel):
    all: list[Condition] = Field(default_factory=list)
    any: list[Condition] = Field(default_factory=list)


class PolicyRule(BaseModel):
    id: str
    motion: PrimaryMotion
    when: ConditionGroup
    score: int
    reason_codes: list[str] = Field(default_factory=list)
    text: str | None = None
    blocking_flags: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class PolicyPack(BaseModel):
    id: str
    version: str
    schema_version: str = POLICY_SCHEMA_VERSION
    approved_by: str | None = None
    approved_at_utc: str | None = None
    approval_notes: str | None = None
    compatible_schema_versions: dict[str, str] = Field(default_factory=dict)
    rules: list[PolicyRule]


class RuleTrace(BaseModel):
    rule_id: str
    motion: PrimaryMotion
    fired: bool
    score_delta: int
    reason_codes: list[str] = Field(default_factory=list)
    text: str | None = None
    condition_trace: str


class MotionAssessment(BaseModel):
    motion: PrimaryMotion
    score: int
    reason_codes: list[str]
    reason_text: list[str]
    rule_traces: list[RuleTrace]
    blocking_flags: list[str] = Field(default_factory=list)
    allocation_only_rightsizing: bool = False


class PolicyEvaluation(BaseModel):
    policy_id: str
    policy_version: str
    motion_assessments: list[MotionAssessment]


MOTION_BASE_TEXT = {
    "MIGRATION_REVIEW": "migration review candidate",
    "ARCHIVE_REVIEW": "archive review candidate",
    "RIGHTSIZING_REVIEW": "allocation right-sizing review candidate",
    "DR_TIER_REVIEW": "DR tier review candidate",
}

MOTION_ORDER = {
    "MIGRATION_REVIEW": 0,
    "ARCHIVE_REVIEW": 1,
    "RIGHTSIZING_REVIEW": 2,
    "DR_TIER_REVIEW": 3,
}


def _condition(field: str, op: ConditionOp, value: Any = None, threshold: str | None = None) -> Condition:
    return Condition(field=field, op=op, value=value, threshold=threshold)


def _all(*conditions: Condition) -> ConditionGroup:
    return ConditionGroup(all=list(conditions))


def _any(*conditions: Condition) -> ConditionGroup:
    return ConditionGroup(any=list(conditions))


DEFAULT_POLICY_PACK = PolicyPack(
    id="default",
    version="1.0.0",
    approved_by="project-maintainers",
    approved_at_utc="2026-04-30T00:00:00Z",
    approval_notes="Default deterministic MVP policy.",
    compatible_schema_versions={
        "evidence": "1.0.0",
        "feature": "1.0.0",
        "policy": "1.0.0",
        "assessment": "1.0.0",
        "trace": "1.0.0",
    },
    rules=[
        PolicyRule(
            id="migration.powered_on",
            motion="MIGRATION_REVIEW",
            when=_all(_condition("powered_on", "eq", True)),
            score=20,
            text="powered on",
        ),
        PolicyRule(
            id="migration.recent_backup",
            motion="MIGRATION_REVIEW",
            when=_all(_condition("has_recent_backup", "eq", True)),
            score=20,
            reason_codes=["RECENT_BACKUP"],
            text="recent restore point",
        ),
        PolicyRule(
            id="migration.low_change_rate",
            motion="MIGRATION_REVIEW",
            when=_all(_condition("low_change_rate", "eq", True)),
            score=20,
            reason_codes=["LOW_CHANGE_RATE"],
            text="low daily change rate",
        ),
        PolicyRule(
            id="migration.small_storage",
            motion="MIGRATION_REVIEW",
            when=_all(_condition("in_use_mib", "lt", threshold="small_workload_mib")),
            score=15,
            reason_codes=["SMALL_STORAGE_FOOTPRINT"],
            text="small storage footprint",
        ),
        PolicyRule(
            id="migration.os_present",
            motion="MIGRATION_REVIEW",
            when=_all(_condition("os_unknown", "eq", False)),
            score=10,
            text="OS present",
        ),
        PolicyRule(
            id="migration.no_snapshot",
            motion="MIGRATION_REVIEW",
            when=_all(_condition("snapshot_present", "eq", False)),
            score=10,
            text="no snapshot risk detected",
        ),
        PolicyRule(
            id="migration.snapshot_present",
            motion="MIGRATION_REVIEW",
            when=_all(_condition("snapshot_present", "eq", True)),
            score=-25,
            reason_codes=["SNAPSHOT_PRESENT"],
            text="snapshot present",
            blocking_flags=["SNAPSHOT_PRESENT"],
        ),
        PolicyRule(
            id="migration.no_backup_match",
            motion="MIGRATION_REVIEW",
            when=_all(_condition("backup_matched", "eq", False)),
            score=-20,
            reason_codes=["NO_BACKUP_MATCH"],
            text="no backup match",
            blocking_flags=["NO_BACKUP_MATCH"],
        ),
        PolicyRule(
            id="archive.powered_off",
            motion="ARCHIVE_REVIEW",
            when=_all(_condition("powered_off", "eq", True)),
            score=35,
            reason_codes=["POWERED_OFF"],
            text="powered off",
        ),
        PolicyRule(
            id="archive.stale_backup",
            motion="ARCHIVE_REVIEW",
            when=_all(_condition("stale_backup", "eq", True)),
            score=20,
            reason_codes=["STALE_BACKUP"],
            text="stale restore point",
        ),
        PolicyRule(
            id="archive.stale_inventory_seen",
            motion="ARCHIVE_REVIEW",
            when=_all(_condition("stale_inventory_seen", "eq", True)),
            score=15,
            reason_codes=["STALE_INVENTORY_SEEN"],
            text="stale inventory last-seen date",
        ),
        PolicyRule(
            id="archive.small_storage",
            motion="ARCHIVE_REVIEW",
            when=_all(_condition("in_use_mib", "lt", threshold="small_workload_mib")),
            score=15,
            text="small storage footprint",
        ),
        PolicyRule(
            id="archive.no_backup_match",
            motion="ARCHIVE_REVIEW",
            when=_all(_condition("backup_matched", "eq", False)),
            score=15,
            reason_codes=["NO_BACKUP_MATCH"],
            text="no backup match",
            blocking_flags=["NO_BACKUP_MATCH"],
        ),
        PolicyRule(
            id="archive.unknown_os",
            motion="ARCHIVE_REVIEW",
            when=_all(_condition("os_unknown", "eq", True)),
            score=10,
            reason_codes=["UNKNOWN_OS"],
            text="OS missing or unknown",
        ),
        PolicyRule(
            id="archive.powered_on_penalty",
            motion="ARCHIVE_REVIEW",
            when=_all(_condition("powered_on", "eq", True)),
            score=-25,
            text="powered on",
        ),
        PolicyRule(
            id="rightsizing.idle_cpu",
            motion="RIGHTSIZING_REVIEW",
            when=_all(
                _condition("cpu_usage_pct", "lte", threshold="idle_cpu_pct"),
                _condition("cpu_count", "gte", 4),
            ),
            score=30,
            reason_codes=["IDLE_CPU"],
            text="low CPU utilization with notable allocation",
            tags=["utilization_signal"],
        ),
        PolicyRule(
            id="rightsizing.high_allocated_cpu",
            motion="RIGHTSIZING_REVIEW",
            when=_all(
                _condition("cpu_usage_pct", "missing"),
                _condition("high_allocated_cpu", "eq", True),
            ),
            score=20,
            reason_codes=["HIGH_ALLOCATED_CPU_REVIEW"],
            text="high allocated CPU needs validation",
            tags=["allocation_signal"],
        ),
        PolicyRule(
            id="rightsizing.oversized_memory",
            motion="RIGHTSIZING_REVIEW",
            when=_all(
                _condition("memory_usage_pct", "lte", threshold="low_memory_usage_pct"),
                _condition("memory_mib", "gte", 16384),
            ),
            score=30,
            reason_codes=["OVERSIZED_MEMORY"],
            text="low memory utilization with notable allocation",
            tags=["utilization_signal"],
        ),
        PolicyRule(
            id="rightsizing.high_allocated_memory",
            motion="RIGHTSIZING_REVIEW",
            when=_all(
                _condition("memory_usage_pct", "missing"),
                _condition("high_allocated_memory", "eq", True),
            ),
            score=20,
            reason_codes=["HIGH_ALLOCATED_MEMORY_REVIEW"],
            text="high allocated memory needs validation",
            tags=["allocation_signal"],
        ),
        PolicyRule(
            id="rightsizing.low_change_rate",
            motion="RIGHTSIZING_REVIEW",
            when=_all(_condition("low_change_rate", "eq", True)),
            score=10,
            reason_codes=["LOW_CHANGE_RATE"],
            text="low daily change rate",
        ),
        PolicyRule(
            id="rightsizing.utilization_window_qualified",
            motion="RIGHTSIZING_REVIEW",
            when=_all(_condition("utilization_sample_quality", "eq", True)),
            score=5,
            reason_codes=["UTILIZATION_WINDOW_QUALIFIED"],
            text="utilization sample window qualified",
            tags=["utilization_signal"],
        ),
        PolicyRule(
            id="rightsizing.sparse_utilization_window",
            motion="RIGHTSIZING_REVIEW",
            when=_all(
                _condition("utilization_sample_count", "present"),
                _condition("utilization_sample_quality", "eq", False),
            ),
            score=-10,
            reason_codes=["SPARSE_UTILIZATION_WINDOW"],
            text="utilization sample window is sparse",
            blocking_flags=["SPARSE_UTILIZATION_WINDOW"],
        ),
        PolicyRule(
            id="dr.low_change_rate",
            motion="DR_TIER_REVIEW",
            when=_all(_condition("low_change_rate", "eq", True)),
            score=30,
            reason_codes=["LOW_CHANGE_RATE"],
            text="low daily change rate",
        ),
        PolicyRule(
            id="dr.large_backup",
            motion="DR_TIER_REVIEW",
            when=_all(_condition("large_backup_footprint", "eq", True)),
            score=25,
            reason_codes=["LARGE_BACKUP_FOOTPRINT"],
            text="large backup footprint",
        ),
        PolicyRule(
            id="dr.high_backup_to_used_ratio",
            motion="DR_TIER_REVIEW",
            when=_all(_condition("backup_to_used_ratio", "gte", threshold="high_backup_to_used_ratio")),
            score=15,
            reason_codes=["HIGH_BACKUP_TO_USED_RATIO"],
            text="high backup-to-used ratio",
        ),
        PolicyRule(
            id="dr.many_restore_points",
            motion="DR_TIER_REVIEW",
            when=_all(_condition("restore_point_count", "gte", threshold="many_restore_points")),
            score=10,
            reason_codes=["MANY_RESTORE_POINTS"],
            text="many restore points",
        ),
        PolicyRule(
            id="dr.recent_backup",
            motion="DR_TIER_REVIEW",
            when=_all(_condition("has_recent_backup", "eq", True)),
            score=10,
            text="recent restore point",
        ),
        PolicyRule(
            id="dr.long_rpo_review",
            motion="DR_TIER_REVIEW",
            when=_all(_condition("long_rpo_review", "eq", True)),
            score=10,
            reason_codes=["RPO_REVIEW"],
            text="RPO value should be reviewed",
        ),
        PolicyRule(
            id="dr.no_backup_match",
            motion="DR_TIER_REVIEW",
            when=_all(_condition("backup_matched", "eq", False)),
            score=-25,
            reason_codes=["NO_BACKUP_MATCH"],
            text="no backup match",
            blocking_flags=["NO_BACKUP_MATCH"],
        ),
    ],
)


def _facts(workload: ResolvedWorkload, features: FeatureSet) -> dict[str, Any]:
    inventory = workload.inventory
    backup = workload.backup
    facts = {name: feature.value for name, feature in features.features.items()}
    facts.update(
        {
            "in_use_mib": inventory.in_use_mib,
            "cpu_count": inventory.cpu_count,
            "memory_mib": inventory.memory_mib,
            "cpu_usage_pct": inventory.cpu_usage_pct
            if inventory.cpu_usage_pct is not None
            else features.value("cpu_p95_pct"),
            "memory_usage_pct": inventory.memory_usage_pct
            if inventory.memory_usage_pct is not None
            else features.value("memory_p95_pct"),
            "restore_point_count": backup.restore_point_count if backup else None,
        }
    )
    return facts


def _rhs(condition: Condition, thresholds: Thresholds) -> Any:
    if condition.threshold is None:
        return condition.value
    return getattr(thresholds, condition.threshold)


def _eval_condition(condition: Condition, facts: dict[str, Any], thresholds: Thresholds) -> bool:
    value = facts.get(condition.field)
    if condition.op == "present":
        return value is not None
    if condition.op == "missing":
        return value is None
    right = _rhs(condition, thresholds)
    if value is None:
        return False
    if condition.op == "eq":
        return value == right
    if condition.op == "ne":
        return value != right
    if condition.op == "lt":
        return value < right
    if condition.op == "lte":
        return value <= right
    if condition.op == "gt":
        return value > right
    if condition.op == "gte":
        return value >= right
    return False


def _eval_group(group: ConditionGroup, facts: dict[str, Any], thresholds: Thresholds) -> bool:
    all_ok = all(
        _eval_condition(item, facts, thresholds)
        for item in group.all
    )
    any_ok = True
    if group.any:
        any_ok = any(
            _eval_condition(item, facts, thresholds)
            for item in group.any
        )
    return all_ok and any_ok


def _trace_conditions(group: ConditionGroup) -> str:
    parts: list[str] = []
    for condition in group.all:
        rhs = condition.threshold if condition.threshold else repr(condition.value)
        parts.append(f"{condition.field} {condition.op} {rhs}")
    for condition in group.any:
        rhs = condition.threshold if condition.threshold else repr(condition.value)
        parts.append(f"{condition.field} {condition.op} {rhs}")
    return "; ".join(parts)


def _clamp(score: int) -> int:
    return max(0, min(100, score))


def evaluate_policy(
    workload: ResolvedWorkload,
    features: FeatureSet,
    thresholds: Thresholds,
    *,
    policy_pack: PolicyPack = DEFAULT_POLICY_PACK,
) -> PolicyEvaluation:
    facts = _facts(workload, features)
    assessments: list[MotionAssessment] = []
    for motion in MOTION_ORDER:
        score = 0
        reason_codes = [motion]
        reason_text = [MOTION_BASE_TEXT[motion]]
        rule_traces: list[RuleTrace] = []
        blocking_flags: list[str] = []
        allocation_signal = False
        utilization_signal = False
        for rule in policy_pack.rules:
            if rule.motion != motion:
                continue
            fired = _eval_group(rule.when, facts, thresholds)
            if fired:
                score += rule.score
                reason_codes.extend(rule.reason_codes)
                if rule.text:
                    reason_text.append(rule.text)
                for flag in rule.blocking_flags:
                    if flag not in blocking_flags:
                        blocking_flags.append(flag)
                allocation_signal = allocation_signal or "allocation_signal" in rule.tags
                utilization_signal = utilization_signal or "utilization_signal" in rule.tags
            rule_traces.append(
                RuleTrace(
                    rule_id=rule.id,
                    motion=rule.motion,
                    fired=fired,
                    score_delta=rule.score if fired else 0,
                    reason_codes=rule.reason_codes if fired else [],
                    text=rule.text if fired else None,
                    condition_trace=_trace_conditions(rule.when),
                )
            )

        assessments.append(
            MotionAssessment(
                motion=motion,  # type: ignore[arg-type]
                score=_clamp(score),
                reason_codes=reason_codes,
                reason_text=reason_text,
                rule_traces=rule_traces,
                blocking_flags=blocking_flags,
                allocation_only_rightsizing=(
                    motion == "RIGHTSIZING_REVIEW" and allocation_signal and not utilization_signal
                ),
            )
        )

    return PolicyEvaluation(
        policy_id=policy_pack.id,
        policy_version=policy_pack.version,
        motion_assessments=assessments,
    )


def choose_winning_motion(evaluation: PolicyEvaluation) -> MotionAssessment:
    return sorted(
        evaluation.motion_assessments,
        key=lambda assessment: (-assessment.score, MOTION_ORDER[assessment.motion]),
    )[0]


def load_policy_pack(path: Path | None) -> PolicyPack:
    if path is None:
        return DEFAULT_POLICY_PACK
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TriageError(f"Could not read policy file {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise TriageError(f"Could not parse policy YAML {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TriageError("Policy file must contain a YAML mapping.")
    try:
        return PolicyPack(**raw)
    except Exception as exc:
        raise TriageError(f"Invalid policy file {path}: {exc}") from exc
