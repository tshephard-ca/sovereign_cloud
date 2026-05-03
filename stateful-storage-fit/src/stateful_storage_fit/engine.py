from __future__ import annotations

from pathlib import Path
from hashlib import sha256
from typing import Optional

from .calibration import apply_calibration
from .classify_mounts import any_non_candidate_network_fs, classify_candidate_mounts
from .classify_processes import classify_processes
from .config import load_thresholds
from .deep_analysis import attach_deep_analysis, build_deep_analysis
from .fit_rules import build_fit_result
from .models import AnalysisBundle, DfFilesystem, FstabEntry, IoDeviceSample, MountEntry, ProcessEntry
from .parse_df import parse_df_file
from .parse_fstab import parse_fstab_file
from .parse_iostat import parse_iostat_file
from .parse_mount import parse_mount_file
from .parse_processes import parse_processes_file
from .policy_packs import PolicyPackError, apply_policy_pack, load_policy_pack
from .storage_profile import StorageProfileError, parse_storage_profile_file


def _add_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _enrich_result_with_extra(result, candidates, extra_evidence: dict | None) -> None:
    extra = extra_evidence or {}
    result.evidence.setdefault("supplemental_evidence", {})
    if "bundle_validation" in extra:
        validation = extra["bundle_validation"]
        result.evidence["supplemental_evidence"]["bundle_quality"] = {
            "core": validation.get("core_completeness_score"),
            "topology": validation.get("topology_completeness_score"),
            "application": validation.get("application_evidence_score"),
            "redaction": validation.get("redaction_preservation_score"),
            "overall": validation.get("overall_bundle_quality_score", validation.get("bundle_quality_score")),
        }
        if validation.get("topology_completeness_score", 1) < 0.5:
            _add_unique(result.warnings, "TOPOLOGY_EVIDENCE_LOW")
    findmnt_mounts = (extra.get("findmnt_json") or {}).get("mounts", [])
    lsblk_devices = (extra.get("lsblk_json") or {}).get("devices", [])
    inode_sample = (extra.get("inode_df") or {}).get("sample", [])
    path_purpose = ((extra.get("app_metadata") or {}).get("path_purpose") or {}).get("paths", [])
    result.evidence["supplemental_evidence"]["app_metadata_present"] = bool(extra.get("app_metadata"))
    if path_purpose:
        _add_unique(result.reason_codes, "APP_DATA_PATH_DECLARED")
        candidate_paths = {candidate.mount_path for candidate in candidates}
        declared_paths = [item.get("path") for item in path_purpose if isinstance(item, dict)]
        if any(path not in candidate_paths for path in declared_paths):
            _add_unique(result.warnings, "DECLARED_APP_PATH_NOT_OBSERVED_IN_MOUNT_OUTPUT")
    findmnt_targets = {item.get("target"): item for item in findmnt_mounts if isinstance(item, dict)}
    lsblk_by_mount = {item.get("mountpoint"): item for item in lsblk_devices if isinstance(item, dict)}
    lineage = []
    for candidate in candidates:
        if candidate.mount_path in findmnt_targets:
            _add_unique(result.reason_codes, "FINDMNT_CONFIRMED_MOUNT")
            options = str(findmnt_targets[candidate.mount_path].get("options", ""))
            if any(opt in options.split(",") for opt in {"sync", "mand", "nolock", "local_lock=none"}):
                _add_unique(result.reason_codes, "MOUNT_OPTIONS_REVIEW_REQUIRED")
                _add_unique(result.warnings, "MOUNT_OPTIONS_REVIEW_REQUIRED")
            if "[" in str(findmnt_targets[candidate.mount_path].get("source", "")):
                _add_unique(result.reason_codes, "BIND_MOUNT_DETECTED")
        device = lsblk_by_mount.get(candidate.mount_path)
        if device:
            _add_unique(result.reason_codes, "LSBLK_DEVICE_LINEAGE_RESOLVED")
            lineage.append(
                {
                    "mount_path": candidate.mount_path,
                    "device": device.get("name"),
                    "parent": device.get("pkname"),
                    "type": device.get("type"),
                    "fstype": device.get("fstype"),
                    "mapping_confidence": "HIGH" if device.get("pkname") else "MEDIUM",
                }
            )
    if lineage:
        result.evidence["device_lineage"] = lineage
    for line in inode_sample:
        parts = str(line).split()
        if len(parts) >= 6 and parts[-2].endswith("%"):
            try:
                pct = float(parts[-2].rstrip("%"))
            except ValueError:
                continue
            if pct >= 80:
                _add_unique(result.reason_codes, "INODE_PRESSURE_RISK")
                _add_unique(result.warnings, "INODE_PRESSURE_RISK")
                break


def _missing_or_unreadable(path: Path | None) -> bool:
    return path is None or not path.exists() or not path.is_file()


def _file_sha256(path: Path | None) -> str | None:
    if _missing_or_unreadable(path):
        return None
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_optional_file(path: Path | None, parser, missing_name: str, parse_warnings: list[str]):
    if _missing_or_unreadable(path):
        return None, [missing_name]
    try:
        value, warnings = parser(path)
        parse_warnings.extend(warnings)
        if not value:
            return value, [missing_name]
        return value, []
    except OSError as exc:
        parse_warnings.append(f"{missing_name.upper()}_READ_FAILED:{exc}")
        return None, [missing_name]


def analyze_paths(
    *,
    df: Optional[Path] = None,
    mount: Optional[Path] = None,
    fstab: Optional[Path] = None,
    iostat: Optional[Path] = None,
    ps: Optional[Path] = None,
    storage_profile_path: Optional[Path] = None,
    config: Optional[Path] = None,
    policy_pack_path: Optional[Path] = None,
    data_paths: list[str] | None = None,
    strict: bool = False,
    extra_evidence: dict | None = None,
    calibration_report: dict | None = None,
    app_metadata: dict | None = None,
) -> AnalysisBundle:
    if strict:
        if _missing_or_unreadable(df):
            raise ValueError("df is required and must point to a readable file in strict mode")
        if _missing_or_unreadable(mount):
            raise ValueError("mount is required and must point to a readable file in strict mode")
        if _missing_or_unreadable(storage_profile_path):
            raise ValueError("storage profile is required and must point to a readable file in strict mode")

    thresholds = load_thresholds(config)
    try:
        thresholds = apply_policy_pack(thresholds, load_policy_pack(policy_pack_path))
    except PolicyPackError as exc:
        raise ValueError(str(exc)) from exc

    parse_warnings: list[str] = []
    missing_data: list[str] = []

    df_entries: list[DfFilesystem] = []
    mount_entries: list[MountEntry] = []
    fstab_entries: list[FstabEntry] = []
    iostat_samples: dict[str, IoDeviceSample] = {}
    iostat_meta: dict = {"max_observed_await_ms": None, "max_observed_util_pct": None, "reports_seen": 0}
    processes: list[ProcessEntry] = []

    parsed, missing = _parse_optional_file(df, parse_df_file, "df", parse_warnings)
    if parsed is not None:
        df_entries = parsed
    missing_data.extend(missing)
    if strict and missing:
        raise ValueError("df is missing or unparseable")

    parsed, missing = _parse_optional_file(mount, parse_mount_file, "mount", parse_warnings)
    if parsed is not None:
        mount_entries = parsed
    missing_data.extend(missing)
    if strict and missing:
        raise ValueError("mount is missing or unparseable")

    parsed, missing = _parse_optional_file(fstab, parse_fstab_file, "fstab", parse_warnings)
    if parsed is not None:
        fstab_entries = parsed
    missing_data.extend(missing)

    if _missing_or_unreadable(iostat):
        missing_data.append("iostat")
    else:
        try:
            iostat_samples, warnings, iostat_meta = parse_iostat_file(iostat)
            parse_warnings.extend(warnings)
            if not iostat_samples:
                missing_data.append("iostat")
        except OSError as exc:
            parse_warnings.append(f"IOSTAT_READ_FAILED:{exc}")
            missing_data.append("iostat")

    parsed, missing = _parse_optional_file(ps, parse_processes_file, "ps", parse_warnings)
    if parsed is not None:
        processes = parsed
    missing_data.extend(missing)

    profile = None
    profile_error = None
    if _missing_or_unreadable(storage_profile_path):
        missing_data.append("storage_profile")
        profile_error = "storage profile is missing"
    else:
        try:
            profile = parse_storage_profile_file(storage_profile_path)
        except StorageProfileError as exc:
            profile_error = str(exc)
            missing_data.append("storage_profile")
            if strict:
                raise ValueError(f"invalid storage profile: {exc}") from exc

    process_info = classify_processes(processes)
    declared_data_paths = []
    if app_metadata:
        declared_data_paths = app_metadata.get("declared_data_paths") or []
    candidates, mount_warnings, uncertain_mapping = classify_candidate_mounts(
        df_entries,
        mount_entries,
        fstab_entries,
        iostat_samples,
        thresholds,
        list(dict.fromkeys([*(data_paths or []), *declared_data_paths])),
    )
    parse_warnings.extend(mount_warnings)
    if strict and not candidates:
        raise ValueError("no candidate data mount detected")

    non_candidate_network = any_non_candidate_network_fs(candidates, mount_entries, fstab_entries)
    result = build_fit_result(
        candidates=candidates,
        mounts_network_elsewhere=non_candidate_network,
        process_info=process_info,
        profile=profile,
        profile_error=profile_error,
        iostat_samples=iostat_samples,
        iostat_meta=iostat_meta,
        missing_data=missing_data,
        parse_warnings=parse_warnings,
        uncertain_mapping=uncertain_mapping,
        config=thresholds,
    )
    result.evidence["engine_policy"] = {
        "engine_version": "storage-inference-v1",
        "thresholds": thresholds,
        "config_path": str(config) if config else None,
        "config_sha256": _file_sha256(config),
        "policy_pack_path": str(policy_pack_path) if policy_pack_path else None,
        "policy_pack_sha256": _file_sha256(policy_pack_path),
    }
    merged_extra = dict(extra_evidence or {})
    if app_metadata:
        merged_extra["app_metadata"] = app_metadata
        result.evidence["app_metadata"] = app_metadata
    _enrich_result_with_extra(result, candidates, merged_extra)
    analysis = build_deep_analysis(
        fit_result=result,
        candidates=candidates,
        process_info=process_info,
        profile=profile,
        iostat_samples=iostat_samples,
        missing_data=missing_data,
        parse_warnings=parse_warnings,
        extra_evidence=merged_extra,
    )
    attach_deep_analysis(result, analysis)
    apply_calibration(result, calibration_report)
    return AnalysisBundle(
        result=result,
        candidate_mounts=candidates,
        parse_warnings=parse_warnings,
        missing_data=missing_data,
    )
