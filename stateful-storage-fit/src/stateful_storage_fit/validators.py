from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from .app_metadata import load_path_purpose
from .classify_mounts import COMMON_DATA_PATHS, is_network_fs
from .parse_iostat import parse_iostat_text
from .parse_mount import parse_mount_text
from .workflow import validate_bundle


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_decision(path: Path) -> dict[str, Any]:
    data = _load_json(path)
    issues: list[str] = []
    warnings: list[str] = []
    if data.get("fit_status") not in {"PASS", "REVIEW", "FAIL"}:
        issues.append("FIT_STATUS_INVALID_OR_MISSING")
    if not isinstance(data.get("analysis"), dict):
        issues.append("ANALYSIS_MISSING")
    if data.get("confidence") == "HIGH":
        missing = set(data.get("missing_data") or [])
        if missing & {"iostat", "ps", "candidate_data_mount", "iostat_device_mapping"}:
            issues.append("HIGH_CONFIDENCE_WITH_CRITICAL_MISSING_DATA")
        readiness = ((data.get("analysis") or {}).get("calibration") or {}).get("readiness_level")
        if readiness in {"RESEARCH_ONLY", "UNKNOWN"}:
            issues.append("HIGH_CONFIDENCE_WITH_UNCALIBRATED_RESEARCH_ONLY_CORPUS")
    if data.get("fit_status") == "PASS" and data.get("blockers"):
        issues.append("PASS_WITH_BLOCKERS")
    if data.get("required_access_mode") == "ReadWriteMany" and "SHARED_FS_DETECTED" not in data.get("reason_codes", []):
        issues.append("RWX_WITHOUT_SHARED_FILESYSTEM_REASON")
    if data.get("required_volume_mode") == "Block" and "RAW_BLOCK_HINT" not in data.get("reason_codes", []):
        issues.append("BLOCK_WITHOUT_RAW_BLOCK_REASON")
    for mount in (data.get("analysis") or {}).get("evidence_graph", {}).get("observations", []):
        subject = mount.get("subject")
        if isinstance(subject, str) and subject.startswith("path_"):
            issues.append("BROKEN_PATH_REDACTION_NON_ABSOLUTE")
            break
    if data.get("storage_request_gib") is not None and data["storage_request_gib"] < 0:
        issues.append("NEGATIVE_STORAGE_REQUEST")
    if data.get("fit_status") == "REVIEW" and not (data.get("analysis") or {}).get("evidence_questions"):
        warnings.append("REVIEW_WITHOUT_EVIDENCE_QUESTIONS")
    return {"schema_version": "1.0", "valid": not issues, "issues": issues, "warnings": warnings}


def validate_input_realism(
    *,
    bundle_dir: Path,
    storage_profile: Path | None = None,
    path_purpose: Path | None = None,
) -> dict[str, Any]:
    bundle = validate_bundle(bundle_dir)
    issues: list[str] = []
    warnings: list[str] = []
    if not bundle.get("valid"):
        issues.append("BUNDLE_INVALID")
    if not (bundle_dir / "manifest.json").exists():
        issues.append("COLLECTOR_MANIFEST_MISSING")
    redaction_mode = bundle.get("redaction_mode", "")
    if redaction_mode.startswith("redact_first") and not (bundle_dir / "redaction-map.json").exists():
        issues.append("REDACTION_MAP_MISSING")
    df_text = (bundle_dir / "df.txt").read_text(encoding="utf-8", errors="replace") if (bundle_dir / "df.txt").exists() else ""
    mount_text = (bundle_dir / "mount.txt").read_text(encoding="utf-8", errors="replace") if (bundle_dir / "mount.txt").exists() else ""
    if re.search(r"\s(path_\d+)(\s|$)", df_text + "\n" + mount_text):
        issues.append("NON_ABSOLUTE_REDACTED_PATHS_PRESENT")
    try:
        mounts, _ = parse_mount_text(mount_text)
    except Exception:
        mounts = []
    network_mounts = {"data_like": [], "system_or_session": [], "unknown": []}
    for mount in mounts:
        if not is_network_fs(mount.fs_type):
            continue
        if mount.mount_path in COMMON_DATA_PATHS or mount.mount_path.startswith(("/data/", "/srv/", "/var/lib/", "/var/www/")):
            network_mounts["data_like"].append(mount.mount_path)
        elif mount.mount_path.startswith(("/run/", "/proc/", "/sys/", "/dev/")):
            network_mounts["system_or_session"].append(mount.mount_path)
        else:
            network_mounts["unknown"].append(mount.mount_path)
    if network_mounts["unknown"]:
        warnings.append("NETWORK_FILESYSTEM_CONTEXT_UNKNOWN")
    ps_text = (bundle_dir / "ps.txt").read_text(encoding="utf-8", errors="replace") if (bundle_dir / "ps.txt").exists() else ""
    process_names = [line.split()[1] if len(line.split()) > 1 and line.split()[0].isdigit() else line.split()[0] for line in ps_text.splitlines() if line.split()]
    useful_processes = [name for name in process_names if name not in {"ps", "bwrap", "sh", "bash"}]
    if not useful_processes:
        warnings.append("PROCESS_EVIDENCE_HAS_NO_USEFUL_WORKLOAD_FAMILY")
    if path_purpose is None:
        warnings.append("APP_PATH_PURPOSE_NOT_DECLARED")
        path_purpose_quality_score = 0.0
    else:
        try:
            path_purpose_data = load_path_purpose(path_purpose)
            declared_paths = [item["path"] for item in path_purpose_data.get("paths", [])]
        except ValueError as exc:
            issues.append(f"PATH_PURPOSE_INVALID:{exc}")
            declared_paths = []
            path_purpose_data = {"paths": []}
        observed_paths = {mount.mount_path for mount in mounts}
        unobserved = [path for path in declared_paths if path not in observed_paths]
        if unobserved:
            warnings.append("DECLARED_APP_PATH_NOT_OBSERVED_IN_MOUNT_OUTPUT")
        score = 0
        if declared_paths:
            score += 30
        if declared_paths and not unobserved:
            score += 30
        owner_confirmed = [
            item
            for item in path_purpose_data.get("paths", [])
            if str(item.get("owner_confidence", "")).upper() in {"MEDIUM", "HIGH"}
        ]
        if owner_confirmed:
            score += 25
        if all(str(item.get("purpose", "")).lower() not in {"", "unknown", "owner_required"} for item in path_purpose_data.get("paths", [])):
            score += 15
        path_purpose_quality_score = float(min(score, 100))
    iostat_reports_seen = None
    iostat_text = (bundle_dir / "iostat.txt").read_text(encoding="utf-8", errors="replace") if (bundle_dir / "iostat.txt").exists() else ""
    if iostat_text:
        _, _, iostat_meta = parse_iostat_text(iostat_text)
        iostat_reports_seen = iostat_meta.get("reports_seen")
        if iostat_reports_seen is not None and iostat_reports_seen < 10:
            warnings.append("IOSTAT_SAMPLE_SHORT_FOR_CALIBRATION")
    if storage_profile is not None:
        profile_text = storage_profile.read_text(encoding="utf-8", errors="replace")
        if "standard-rwo" in profile_text and "fast-rwo" in profile_text and "shared-rwx" in profile_text:
            warnings.append("PROFILE_APPEARS_TO_BE_EXAMPLE_GENERIC")
    if bundle.get("topology_completeness_score", 0) < 0.5:
        warnings.append("TOPOLOGY_EVIDENCE_LOW")
    return {
        "schema_version": "1.0",
        "valid": not issues,
        "issues": issues,
        "warnings": warnings,
        "bundle_validation": bundle,
        "network_filesystem_mounts": network_mounts,
        "path_purpose_quality_score": path_purpose_quality_score,
        "iostat_reports_seen": iostat_reports_seen,
        "useful_processes": useful_processes,
    }


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data
