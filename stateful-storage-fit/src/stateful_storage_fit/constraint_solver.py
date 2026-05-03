from __future__ import annotations

from .fit_rules import _tier_rank
from .models import (
    CompatibilityConstraint,
    EnhancedStorageRequirement,
    StorageClassCompatibility,
    StorageClassProfile,
    StorageProfile,
)


def _constraint(
    id_: str,
    level: str,
    description: str,
    required,
    actual,
    satisfied: bool,
    reason_code: str | None = None,
) -> CompatibilityConstraint:
    return CompatibilityConstraint(
        id=id_,
        level=level,
        description=description,
        required=required,
        actual=actual,
        satisfied=satisfied,
        reason_code=reason_code,
    )


def _counterfactual_for(constraint: CompatibilityConstraint) -> str:
    if constraint.id == "access_mode":
        return f"Would match this requirement if the class supported {constraint.required}."
    if constraint.id == "volume_mode":
        return f"Would match this requirement if the class supported {constraint.required} volume mode."
    if constraint.id == "storage_kind":
        return f"Would match this requirement if the class storage_kind were {constraint.required}."
    if constraint.id == "size":
        return f"Would match this requirement if max_size_gib were absent or at least {constraint.required}."
    if constraint.id == "performance_tier":
        return f"Would match this requirement if performance_tier ranked at least {constraint.required}."
    return f"Would match this requirement if {constraint.description.lower()}."


def evaluate_storage_class(
    storage_class: StorageClassProfile,
    profile: StorageProfile,
    requirement: EnhancedStorageRequirement,
) -> StorageClassCompatibility:
    constraints = [
        _constraint(
            "access_mode",
            "hard",
            "Storage class must support the required access mode.",
            requirement.required_access_mode,
            storage_class.access_modes,
            requirement.required_access_mode in storage_class.access_modes,
            "ACCESS_MODE_UNSUPPORTED",
        ),
        _constraint(
            "volume_mode",
            "hard",
            "Storage class must support the required volume mode.",
            requirement.required_volume_mode,
            storage_class.volume_modes,
            requirement.required_volume_mode in storage_class.volume_modes,
            "VOLUME_MODE_UNSUPPORTED",
        ),
    ]
    if requirement.preferred_storage_kind != "unknown":
        constraints.append(
            _constraint(
                "storage_kind",
                "hard",
                "Storage class kind must match the inferred preferred kind.",
                requirement.preferred_storage_kind,
                storage_class.storage_kind,
                storage_class.storage_kind == requirement.preferred_storage_kind,
                "STORAGE_KIND_MISMATCH",
            )
        )
    if requirement.storage_request_gib is not None:
        constraints.append(
            _constraint(
                "size",
                "hard",
                "Storage class max_size_gib must satisfy requested size when max_size_gib is present.",
                requirement.storage_request_gib,
                storage_class.max_size_gib,
                storage_class.max_size_gib is None or storage_class.max_size_gib >= requirement.storage_request_gib,
                "MAX_SIZE_TOO_SMALL",
            )
        )
    constraints.append(
        _constraint(
            "performance_tier",
            "hard",
            "Storage class performance tier must rank at least the required tier.",
            requirement.required_performance_tier,
            storage_class.performance_tier,
            _tier_rank(profile, storage_class.performance_tier) >= _tier_rank(profile, requirement.required_performance_tier),
            "PERFORMANCE_TIER_BELOW_REQUIRED",
        )
    )

    soft_constraints: list[CompatibilityConstraint] = []
    if "supports_expansion_preferred=true" in requirement.soft_preferences:
        soft_constraints.append(
            _constraint(
                "expansion",
                "soft",
                "Expansion support is preferred because observed capacity risk is elevated.",
                True,
                storage_class.supports_expansion,
                storage_class.supports_expansion,
                "EXPANSION_NOT_SUPPORTED",
            )
        )
    if "supports_snapshots_preferred=true" in requirement.soft_preferences:
        soft_constraints.append(
            _constraint(
                "snapshots",
                "soft",
                "Snapshot support is preferred for stateful workload handoff, but is not required by the MVP.",
                True,
                storage_class.supports_snapshots,
                storage_class.supports_snapshots,
                "SNAPSHOTS_NOT_SUPPORTED",
            )
        )

    hard_failures = [item for item in constraints if not item.satisfied]
    soft_warnings = [item for item in soft_constraints if not item.satisfied]
    satisfied = [item for item in constraints + soft_constraints if item.satisfied]
    status = "REJECTED" if hard_failures else "PARTIAL" if soft_warnings else "MATCH"
    score = len(satisfied) * 10 - len(hard_failures) * 100 - len(soft_warnings) * 5
    return StorageClassCompatibility(
        storage_class=storage_class.name,
        status=status,
        hard_failures=hard_failures,
        soft_warnings=soft_warnings,
        satisfied_constraints=satisfied,
        counterfactuals=[_counterfactual_for(item) for item in hard_failures],
        score=score,
    )


def solve_compatibility(
    profile: StorageProfile | None,
    requirement: EnhancedStorageRequirement,
) -> list[StorageClassCompatibility]:
    if profile is None:
        return []
    evaluations = [evaluate_storage_class(storage_class, profile, requirement) for storage_class in profile.storage_classes]
    status_rank = {"MATCH": 0, "PARTIAL": 1, "REJECTED": 2}
    return sorted(evaluations, key=lambda item: (status_rank[item.status], -item.score, item.storage_class))

