from __future__ import annotations

from .features import bytes_to_gib, capacity_risk, latency_risk_for_sample, parent_iostat_device, storage_request_gib
from .models import CandidateDataMount, DfFilesystem, FstabEntry, IoDeviceSample, MountEntry


NETWORK_FS_TYPES = {
    "nfs",
    "nfs4",
    "cifs",
    "smb3",
    "ceph",
    "cephfs",
    "glusterfs",
    "lustre",
    "gpfs",
    "sshfs",
}

EXCLUDED_FS_TYPES = {
    "cgroup",
    "cgroup2",
    "pstore",
    "debugfs",
    "tracefs",
    "securityfs",
    "devpts",
    "overlay",
    "squashfs",
    "autofs",
    "proc",
    "sysfs",
    "tmpfs",
    "devtmpfs",
}

EXCLUDED_MOUNT_PATHS = {
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/boot",
    "/boot/efi",
}

COMMON_DATA_PATHS = {
    "/data",
    "/srv",
    "/opt",
    "/app",
    "/apps",
    "/var/lib",
    "/var/lib/mysql",
    "/var/lib/mariadb",
    "/var/lib/postgresql",
    "/var/lib/pgsql",
    "/var/lib/mongo",
    "/var/lib/cassandra",
    "/var/lib/elasticsearch",
    "/var/lib/redis",
    "/var/www",
    "/home",
}

DB_PATH_HINTS = {
    "/var/lib/mysql",
    "/var/lib/mariadb",
    "/var/lib/postgresql",
    "/var/lib/pgsql",
    "/var/lib/mongo",
    "/var/lib/cassandra",
    "/var/lib/elasticsearch",
    "/var/lib/redis",
}


def is_network_fs(fs_type: str | None) -> bool:
    return (fs_type or "").lower() in NETWORK_FS_TYPES


def _is_excluded_mount(path: str, fs_type: str | None) -> bool:
    fs = (fs_type or "").lower()
    if path in EXCLUDED_MOUNT_PATHS:
        return True
    if path.startswith(("/proc/", "/sys/", "/dev/", "/run/")):
        return True
    if path in {"/tmp", "/var/tmp"} and fs == "tmpfs":
        return True
    return fs in EXCLUDED_FS_TYPES


def _role_for_path(path: str, fs_type: str) -> str:
    if is_network_fs(fs_type):
        return "shared_file"
    if path in DB_PATH_HINTS:
        return "database_data"
    if path.startswith(("/var/www", "/srv")):
        return "content_data"
    if path.startswith(("/opt", "/app", "/apps")):
        return "application_data"
    return "general_data"


def _mount_lookup(mounts: list[MountEntry]) -> dict[str, MountEntry]:
    return {mount.mount_path: mount for mount in mounts}


def _fstab_lookup(fstab_entries: list[FstabEntry]) -> dict[str, FstabEntry]:
    return {entry.mount_path: entry for entry in fstab_entries}


def _df_lookup(df_entries: list[DfFilesystem]) -> dict[str, DfFilesystem]:
    return {entry.mount_path: entry for entry in df_entries}


def _candidate_reason(path: str, used_gib: float | None, config: dict, data_paths: set[str]) -> str | None:
    if path in data_paths:
        return "USER_DATA_PATH"
    if path in COMMON_DATA_PATHS:
        return "KNOWN_DATA_PATH"
    if path == "/":
        return None
    if used_gib is not None and used_gib >= float(config["data_mount_min_used_gib"]):
        return "NON_SYSTEM_MOUNT_WITH_DATA"
    return None


def _candidate_scoring(path: str, fs_type: str, used_gib: float | None, reason: str) -> tuple[float, list[str], str, str]:
    score = 0.0
    reasons: list[str] = []
    if reason == "USER_DATA_PATH":
        score += 60
        reasons.append("USER_DECLARED_DATA_PATH")
    if path in COMMON_DATA_PATHS:
        score += 35
        reasons.append("KNOWN_DATA_PATH")
    if path in DB_PATH_HINTS:
        score += 15
        reasons.append("DATABASE_PATH_HINT")
    if used_gib is not None and used_gib >= 1:
        score += min(25, used_gib / 100)
        reasons.append("USED_CAPACITY_PRESENT")
    if is_network_fs(fs_type):
        score += 10
        reasons.append("SHARED_FILESYSTEM_SIGNAL")
    if reason == "ROOT_ONLY_STORAGE_VIEW":
        score = min(score + 10, 30)
        reasons.append("ROOT_ONLY_FALLBACK")
    if reason == "NON_SYSTEM_MOUNT_WITH_DATA":
        score += 20
        reasons.append("NON_SYSTEM_MOUNT_WITH_DATA")
    score = round(min(score, 100.0), 3)
    if reason == "USER_DATA_PATH":
        ownership = "HIGH"
        false_positive = "LOW"
    elif path in COMMON_DATA_PATHS or path in DB_PATH_HINTS:
        ownership = "MEDIUM"
        false_positive = "MEDIUM"
    elif reason == "ROOT_ONLY_STORAGE_VIEW":
        ownership = "LOW"
        false_positive = "HIGH"
    else:
        ownership = "LOW"
        false_positive = "MEDIUM" if score >= 30 else "HIGH"
    return score, reasons, ownership, false_positive


def classify_candidate_mounts(
    df_entries: list[DfFilesystem],
    mounts: list[MountEntry],
    fstab_entries: list[FstabEntry],
    iostat_samples: dict[str, IoDeviceSample],
    config: dict,
    data_paths: list[str] | None = None,
) -> tuple[list[CandidateDataMount], list[str], bool]:
    warnings: list[str] = []
    uncertain_mapping = False
    data_path_set = set(data_paths or [])
    mount_by_path = _mount_lookup(mounts)
    fstab_by_path = _fstab_lookup(fstab_entries)
    df_by_path = _df_lookup(df_entries)

    paths = sorted(set(mount_by_path) | set(df_by_path))
    candidates: list[CandidateDataMount] = []
    root_candidate: CandidateDataMount | None = None

    for path in paths:
        df = df_by_path.get(path)
        mount = mount_by_path.get(path)
        fstab = fstab_by_path.get(path)
        fs_type = (mount.fs_type if mount else None) or (df.fs_type if df else None) or (fstab.fs_type if fstab else None) or "unknown"
        source = (mount.source if mount else None) or (df.filesystem if df else None) or (fstab.source if fstab else None) or "unknown"
        used_gib = bytes_to_gib(df.used_bytes if df else None)
        available_gib = bytes_to_gib(df.available_bytes if df else None)

        if _is_excluded_mount(path, fs_type):
            continue

        reason = _candidate_reason(path, used_gib, config, data_path_set)
        is_root_fallback = False
        if reason is None and path == "/":
            is_root_fallback = True
            reason = "ROOT_ONLY_STORAGE_VIEW"
        if reason is None:
            continue

        score, score_reasons, ownership_confidence, false_positive_risk = _candidate_scoring(
            path, fs_type, used_gib, reason
        )

        device_name, uncertain = parent_iostat_device(source)
        if uncertain:
            uncertain_mapping = True
        sample = iostat_samples.get(device_name) if device_name else None
        if device_name and iostat_samples and sample is None and not is_network_fs(fs_type):
            uncertain_mapping = True

        candidate = CandidateDataMount(
            mount_path=path,
            source=source,
            fs_type=fs_type,
            used_gib=round(used_gib, 3) if used_gib is not None else None,
            available_gib=round(available_gib, 3) if available_gib is not None else None,
            capacity_used_pct=df.capacity_pct if df else None,
            data_mount_reason=reason,
            inferred_role=_role_for_path(path, fs_type),
            device_from_iostat=sample.device if sample else device_name,
            await_ms=sample.max_await_ms if sample and sample.max_await_ms is not None else (sample.await_ms if sample else None),
            util_pct=sample.max_util_pct if sample and sample.max_util_pct is not None else (sample.util_pct if sample else None),
            capacity_risk=capacity_risk(df.capacity_pct if df else None, config),
            latency_risk=latency_risk_for_sample(sample, config),
            candidate_score=score,
            candidate_score_reasons=score_reasons,
            ownership_confidence=ownership_confidence,
            false_positive_risk=false_positive_risk,
            notes=[],
        )
        if is_root_fallback:
            root_candidate = candidate
        else:
            candidates.append(candidate)

    if not candidates and root_candidate is not None:
        candidates.append(root_candidate)

    if not candidates:
        warnings.append("NO_CANDIDATE_DATA_MOUNT")
    return candidates, warnings, uncertain_mapping


def total_storage_request_gib(candidates: list[CandidateDataMount], config: dict) -> int | None:
    requests = [storage_request_gib(candidate.used_gib, config) for candidate in candidates]
    present = [request for request in requests if request is not None]
    if not present:
        return None
    return sum(present)


def any_candidate_network_fs(candidates: list[CandidateDataMount]) -> bool:
    return any(is_network_fs(candidate.fs_type) for candidate in candidates)


def any_non_candidate_network_fs(
    candidates: list[CandidateDataMount],
    mounts: list[MountEntry],
    fstab_entries: list[FstabEntry],
) -> bool:
    candidate_paths = {candidate.mount_path for candidate in candidates}
    for mount in mounts:
        if mount.mount_path not in candidate_paths and is_network_fs(mount.fs_type):
            return True
    for entry in fstab_entries:
        if entry.mount_path not in candidate_paths and is_network_fs(entry.fs_type):
            return True
    return False
