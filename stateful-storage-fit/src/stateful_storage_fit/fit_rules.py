from __future__ import annotations

from typing import Iterable

from .classify_mounts import (
    any_candidate_network_fs,
    any_non_candidate_network_fs,
    is_network_fs,
    total_storage_request_gib,
)
from .classify_processes import ProcessClassification
from .features import latency_risk_from_values, worst_risk
from .models import (
    CandidateDataMount,
    FitResult,
    IoDeviceSample,
    RejectedStorageClass,
    StorageClassProfile,
    StorageProfile,
    StorageRequirement,
)


def _add_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _add_many(values: list[str], candidates: Iterable[str]) -> None:
    for value in candidates:
        _add_unique(values, value)


def _tier_rank(profile: StorageProfile, tier: str) -> int:
    return int(profile.performance_tiers.get(tier, 0))


def _global_latency_risk(iostat_samples: dict[str, IoDeviceSample], config: dict) -> str:
    if not iostat_samples:
        return "UNKNOWN"
    await_values = [
        sample.max_await_ms if sample.max_await_ms is not None else sample.await_ms
        for sample in iostat_samples.values()
        if not sample.device.startswith(("loop", "ram"))
    ]
    util_values = [
        sample.max_util_pct if sample.max_util_pct is not None else sample.util_pct
        for sample in iostat_samples.values()
        if not sample.device.startswith(("loop", "ram"))
    ]
    queue_values = [
        sample.queue_depth for sample in iostat_samples.values() if not sample.device.startswith(("loop", "ram"))
    ]
    max_await = max([value for value in await_values if value is not None], default=None)
    max_util = max([value for value in util_values if value is not None], default=None)
    max_queue = max([value for value in queue_values if value is not None], default=None)
    return latency_risk_from_values(max_await, max_util, max_queue, config)


def _required_performance_tier(
    process_info: ProcessClassification,
    latency_risk: str,
    config: dict,
) -> str:
    if (
        latency_risk == "HIGH"
        and (process_info.database_processes or process_info.stateful_processes)
        and config.get("require_low_latency_if_latency_high")
    ):
        return "low_latency"
    if (
        latency_risk == "HIGH"
        and (process_info.database_processes or process_info.stateful_processes)
        and config.get("db_requires_fast_if_latency_high", True)
    ):
        return "fast"
    return "standard"


def derive_requirement(
    candidates: list[CandidateDataMount],
    process_info: ProcessClassification,
    iostat_samples: dict[str, IoDeviceSample],
    config: dict,
    reason_codes: list[str],
    warnings: list[str],
) -> tuple[StorageRequirement, str, str]:
    request_gib = total_storage_request_gib(candidates, config)
    shared_candidate = any_candidate_network_fs(candidates)

    if shared_candidate:
        required_access_mode = "ReadWriteMany"
        preferred_kind = "file"
        _add_many(reason_codes, ["SHARED_FS_DETECTED", "RWX_REQUIRED", "FILE_STORAGE_REQUIRED"])
    else:
        required_access_mode = "ReadWriteOnce"
        preferred_kind = "unknown"
        _add_unique(reason_codes, "RWO_REQUIRED")

    if process_info.database_processes:
        _add_unique(reason_codes, "DB_PROCESS_DETECTED")
        if not shared_candidate and config.get("db_prefers_block_storage", True):
            preferred_kind = "block"
            _add_unique(reason_codes, "BLOCK_STORAGE_PREFERRED")
    if process_info.stateful_processes:
        _add_unique(reason_codes, "STATEFUL_PROCESS_DETECTED")
        if not shared_candidate:
            preferred_kind = "block"
            _add_unique(reason_codes, "BLOCK_STORAGE_PREFERRED")
    if process_info.file_server_processes:
        _add_many(reason_codes, ["FILE_SERVER_PROCESS_DETECTED", "HUMAN_ARCHITECTURE_REVIEW_REQUIRED"])

    if candidates:
        _add_unique(reason_codes, "DATA_MOUNT_DETECTED")
    if any(candidate.data_mount_reason == "ROOT_ONLY_STORAGE_VIEW" for candidate in candidates):
        _add_unique(reason_codes, "ROOT_ONLY_STORAGE_VIEW")

    candidate_latency = worst_risk([candidate.latency_risk for candidate in candidates])
    if candidate_latency == "UNKNOWN" and iostat_samples:
        candidate_latency = _global_latency_risk(iostat_samples, config)
    latency_risk = candidate_latency
    if latency_risk == "UNKNOWN":
        _add_unique(reason_codes, "IOSTAT_MISSING")
    else:
        _add_unique(reason_codes, f"LATENCY_RISK_{latency_risk}")

    capacity = worst_risk([candidate.capacity_risk for candidate in candidates])
    if not candidates:
        capacity = "UNKNOWN"
    if capacity != "UNKNOWN":
        _add_unique(reason_codes, f"CAPACITY_RISK_{capacity}")

    required_volume_mode = "Filesystem"
    if process_info.raw_block_required:
        required_volume_mode = "Block"
        _add_unique(reason_codes, "RAW_BLOCK_HINT")
    elif process_info.raw_block_hint:
        _add_many(reason_codes, ["RAW_BLOCK_HINT", "RAW_BLOCK_REVIEW_REQUIRED"])
        _add_unique(warnings, "RAW_BLOCK_REVIEW_REQUIRED")

    required_tier = _required_performance_tier(process_info, latency_risk, config)
    if required_tier == "fast":
        _add_unique(reason_codes, "FAST_STORAGE_RECOMMENDED")
    elif required_tier == "low_latency":
        _add_unique(reason_codes, "LOW_LATENCY_STORAGE_RECOMMENDED")

    return (
        StorageRequirement(
            required_access_mode=required_access_mode,
            required_volume_mode=required_volume_mode,
            preferred_storage_kind=preferred_kind,
            storage_request_gib=request_gib,
            required_performance_tier=required_tier,
        ),
        capacity,
        latency_risk,
    )


def _rejection_reasons(
    storage_class: StorageClassProfile,
    requirement: StorageRequirement,
    profile: StorageProfile,
) -> list[str]:
    reasons: list[str] = []
    if requirement.required_access_mode not in storage_class.access_modes:
        reasons.append("ACCESS_MODE_UNSUPPORTED")
    if requirement.required_volume_mode not in storage_class.volume_modes:
        reasons.append("VOLUME_MODE_UNSUPPORTED")
    if (
        requirement.preferred_storage_kind != "unknown"
        and storage_class.storage_kind != requirement.preferred_storage_kind
    ):
        reasons.append("STORAGE_KIND_MISMATCH")
    if (
        requirement.storage_request_gib is not None
        and storage_class.max_size_gib is not None
        and storage_class.max_size_gib < requirement.storage_request_gib
    ):
        reasons.append("MAX_SIZE_TOO_SMALL")
    if _tier_rank(profile, storage_class.performance_tier) < _tier_rank(profile, requirement.required_performance_tier):
        reasons.append("PERFORMANCE_TIER_BELOW_REQUIRED")
    return reasons


def match_storage_classes(
    profile: StorageProfile,
    requirement: StorageRequirement,
    capacity_risk: str,
) -> tuple[list[StorageClassProfile], list[RejectedStorageClass]]:
    matches: list[StorageClassProfile] = []
    rejected: list[RejectedStorageClass] = []
    for storage_class in profile.storage_classes:
        reasons = _rejection_reasons(storage_class, requirement, profile)
        if reasons:
            rejected.append(RejectedStorageClass(name=storage_class.name, reasons=reasons))
        else:
            matches.append(storage_class)

    def rank_key(storage_class: StorageClassProfile) -> tuple[int, int, int, str]:
        expandable_score = 0 if capacity_risk in {"MEDIUM", "HIGH"} and storage_class.supports_expansion else 1
        snapshot_score = 0 if storage_class.supports_snapshots else 1
        return (_tier_rank(profile, storage_class.performance_tier), expandable_score, snapshot_score, storage_class.name)

    matches.sort(key=rank_key)
    rejected.sort(key=lambda item: item.name)
    return matches, rejected


def _capacity_profile_adjustments(
    profile: StorageProfile,
    requirement: StorageRequirement,
    rejected: list[RejectedStorageClass],
    blockers: list[str],
    reason_codes: list[str],
    capacity_risk: str,
) -> str:
    if requirement.storage_request_gib is None:
        return capacity_risk
    size_rejected = [item for item in rejected if "MAX_SIZE_TOO_SMALL" in item.reasons]
    otherwise_compatible_size_rejected = [
        item for item in size_rejected if set(item.reasons) == {"MAX_SIZE_TOO_SMALL"}
    ]
    if otherwise_compatible_size_rejected:
        _add_unique(reason_codes, "CAPACITY_EXCEEDS_AVAILABLE_PROFILE")
        if not any(
            "MAX_SIZE_TOO_SMALL" not in _rejection_reasons(storage_class, requirement, profile)
            for storage_class in profile.storage_classes
        ):
            _add_unique(blockers, "CAPACITY_EXCEEDS_AVAILABLE_PROFILE")
            return "HIGH"
        if capacity_risk == "LOW":
            return "MEDIUM"
    return capacity_risk


def _sync_capacity_reason_code(reason_codes: list[str], capacity_risk: str) -> None:
    for code in ["CAPACITY_RISK_LOW", "CAPACITY_RISK_MEDIUM", "CAPACITY_RISK_HIGH"]:
        while code in reason_codes:
            reason_codes.remove(code)
    if capacity_risk != "UNKNOWN":
        _add_unique(reason_codes, f"CAPACITY_RISK_{capacity_risk}")


def _confidence(
    missing_data: list[str],
    candidates: list[CandidateDataMount],
    matches: list[StorageClassProfile],
    uncertain_mapping: bool,
    process_info: ProcessClassification,
) -> str:
    if "df" in missing_data or "mount" in missing_data or "storage_profile" in missing_data:
        return "LOW"
    if not candidates or "candidate_data_mount" in missing_data:
        return "LOW"
    if "iostat" in missing_data and "ps" in missing_data:
        return "LOW"
    if missing_data or uncertain_mapping or process_info.command_only:
        return "MEDIUM"
    if len(matches) != 1:
        return "MEDIUM"
    return "HIGH"


def _reason_text(reason_codes: list[str], capacity_risk: str, latency_risk: str) -> list[str]:
    text: list[str] = []
    if "DB_PROCESS_DETECTED" in reason_codes:
        text.append("Database-like process detected, so block-backed filesystem storage is preferred unless shared filesystem evidence is present.")
    if "STATEFUL_PROCESS_DETECTED" in reason_codes:
        text.append("Stateful service process detected; process names are storage-fit hints, not full application discovery.")
    if "SHARED_FS_DETECTED" in reason_codes:
        text.append("A candidate data mount uses a shared or network filesystem, so ReadWriteMany filesystem storage is required.")
    if "FILE_SERVER_PROCESS_DETECTED" in reason_codes:
        text.append("File-serving process detected; a human should confirm the intended storage access pattern.")
    if "RAW_BLOCK_HINT" in reason_codes:
        text.append("Raw-device evidence was observed; confirm whether raw Block volume mode is truly required.")
    if latency_risk == "HIGH":
        text.append("iostat shows high latency or utilization on observed storage; latency risk requires deeper storage testing.")
    if capacity_risk == "HIGH":
        text.append("Observed capacity use or requested size creates high capacity risk for the supplied storage profile.")
    elif capacity_risk == "MEDIUM":
        text.append("Observed capacity use or requested size creates medium capacity risk; verify headroom and expansion behavior.")
    if "STORAGE_CLASS_MATCH" in reason_codes:
        text.append("At least one supplied storage class supports the inferred access mode, volume mode, size, storage kind, and performance tier.")
    if "NO_STORAGE_CLASS_MATCH" in reason_codes:
        text.append("No supplied storage class satisfies the inferred storage requirements.")
    if "ROOT_ONLY_STORAGE_VIEW" in reason_codes:
        text.append("Only root filesystem storage was usable as a data candidate, which reduces confidence.")
    if not text:
        text.append("The decision is based only on the supplied local text outputs and storage profile.")
    return text


def build_fit_result(
    *,
    candidates: list[CandidateDataMount],
    mounts_network_elsewhere: bool,
    process_info: ProcessClassification,
    profile: StorageProfile | None,
    profile_error: str | None,
    iostat_samples: dict[str, IoDeviceSample],
    iostat_meta: dict,
    missing_data: list[str],
    parse_warnings: list[str],
    uncertain_mapping: bool,
    config: dict,
) -> FitResult:
    reason_codes: list[str] = []
    warnings: list[str] = []
    blockers: list[str] = []
    rejected: list[RejectedStorageClass] = []
    matches: list[StorageClassProfile] = []

    for warning in parse_warnings:
        if warning.startswith("IOSTAT_PARSE_FAILED"):
            _add_unique(reason_codes, "IOSTAT_PARSE_FAILED")
        elif warning.startswith("PS_PROCESS_ARGS_MISSING"):
            _add_unique(missing_data, "process_args")

    if mounts_network_elsewhere:
        _add_unique(warnings, "NETWORK_FILESYSTEM_ON_NON_DATA_MOUNT")
    if uncertain_mapping:
        _add_many(warnings, ["IOSTAT_DEVICE_MAPPING_UNCERTAIN"])
        _add_unique(reason_codes, "IOSTAT_DEVICE_MAPPING_UNCERTAIN")
        _add_unique(missing_data, "iostat_device_mapping")
    if "iostat" in missing_data:
        _add_unique(warnings, "IOSTAT_MISSING")
        _add_unique(reason_codes, "IOSTAT_MISSING")
    if "ps" in missing_data:
        _add_unique(warnings, "PROCESS_LIST_MISSING")
        _add_unique(reason_codes, "PROCESS_LIST_MISSING")
    if not candidates:
        _add_unique(missing_data, "candidate_data_mount")

    requirement, capacity, latency = derive_requirement(
        candidates,
        process_info,
        iostat_samples,
        config,
        reason_codes,
        warnings,
    )

    if profile is None:
        _add_many(blockers, ["STORAGE_PROFILE_INVALID"])
        _add_unique(missing_data, "storage_profile")
        fit_status = "FAIL"
        confidence = "LOW"
        if profile_error:
            _add_unique(warnings, profile_error)
        return FitResult(
            fit_status=fit_status,
            recommended_storage_class=None,
            required_access_mode=requirement.required_access_mode,
            required_volume_mode=requirement.required_volume_mode,
            preferred_storage_kind=requirement.preferred_storage_kind,
            storage_request_gib=requirement.storage_request_gib,
            capacity_risk=capacity,
            latency_risk=latency,
            confidence=confidence,
            blockers=blockers,
            warnings=warnings,
            reason_codes=reason_codes,
            reason_text=_reason_text(reason_codes, capacity, latency),
            missing_data=sorted(missing_data),
            evidence=_evidence(candidates, process_info, iostat_meta),
            matched_storage_classes=[],
            rejected_storage_classes=[],
        )

    matches, rejected = match_storage_classes(profile, requirement, capacity)
    capacity = _capacity_profile_adjustments(profile, requirement, rejected, blockers, reason_codes, capacity)
    _sync_capacity_reason_code(reason_codes, capacity)

    if any_candidate_network_fs(candidates):
        has_rwx_file = any(
            "ReadWriteMany" in storage_class.access_modes
            and "Filesystem" in storage_class.volume_modes
            and storage_class.storage_kind == "file"
            for storage_class in profile.storage_classes
        )
        if not has_rwx_file:
            _add_many(blockers, ["SHARED_FILESYSTEM_REQUIRED_NO_RWX_PROFILE"])
            _add_unique(reason_codes, "SHARED_FILESYSTEM_REQUIRED_NO_RWX_PROFILE")

    if process_info.raw_block_required:
        has_block = any("Block" in storage_class.volume_modes for storage_class in profile.storage_classes)
        if not has_block:
            _add_many(blockers, ["RAW_BLOCK_REQUIRED_NO_PROFILE"])
            _add_unique(reason_codes, "RAW_BLOCK_REQUIRED_NO_PROFILE")

    if matches:
        _add_unique(reason_codes, "STORAGE_CLASS_MATCH")
    else:
        _add_many(blockers, ["NO_STORAGE_CLASS_MATCH"])
        _add_unique(reason_codes, "NO_STORAGE_CLASS_MATCH")

    review_signals = {
        "iostat",
        "ps",
        "candidate_data_mount",
        "iostat_device_mapping",
        "process_args",
    } & set(missing_data)
    if latency == "HIGH":
        review_signals.add("latency_high")
    if any(candidate.data_mount_reason == "ROOT_ONLY_STORAGE_VIEW" for candidate in candidates):
        review_signals.add("root_only")
    if process_info.file_server_processes:
        review_signals.add("file_server")
    if process_info.raw_block_hint:
        review_signals.add("raw_block_hint")
    if capacity == "HIGH" and any(storage_class.supports_expansion for storage_class in matches):
        review_signals.add("capacity_high_expandable")

    if blockers:
        fit_status = "FAIL"
    elif matches and review_signals:
        fit_status = "REVIEW"
    elif matches and capacity in {"LOW", "MEDIUM"} and latency in {"LOW", "MEDIUM"}:
        fit_status = "PASS"
    elif matches:
        fit_status = "REVIEW"
    else:
        fit_status = "FAIL"

    confidence = _confidence(missing_data, candidates, matches, uncertain_mapping, process_info)
    recommended = matches[0].name if matches else None

    return FitResult(
        fit_status=fit_status,
        recommended_storage_class=recommended,
        required_access_mode=requirement.required_access_mode,
        required_volume_mode=requirement.required_volume_mode,
        preferred_storage_kind=requirement.preferred_storage_kind,
        storage_request_gib=requirement.storage_request_gib,
        capacity_risk=capacity,
        latency_risk=latency,
        confidence=confidence,
        blockers=blockers,
        warnings=warnings,
        reason_codes=reason_codes,
        reason_text=_reason_text(reason_codes, capacity, latency),
        missing_data=sorted(missing_data),
        evidence=_evidence(candidates, process_info, iostat_meta),
        matched_storage_classes=[storage_class.name for storage_class in matches],
        rejected_storage_classes=rejected,
    )


def _evidence(
    candidates: list[CandidateDataMount],
    process_info: ProcessClassification,
    iostat_meta: dict,
) -> dict:
    return {
        "candidate_data_mounts": len(candidates),
        "network_filesystem_mounts": sum(1 for candidate in candidates if is_network_fs(candidate.fs_type)),
        "database_processes_detected": process_info.database_processes,
        "stateful_processes_detected": process_info.stateful_processes,
        "file_server_processes_detected": process_info.file_server_processes,
        "max_observed_await_ms": iostat_meta.get("max_observed_await_ms"),
        "max_observed_util_pct": iostat_meta.get("max_observed_util_pct"),
    }
