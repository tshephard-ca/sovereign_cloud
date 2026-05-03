from __future__ import annotations

from stateful_storage_fit.classify_mounts import any_non_candidate_network_fs, classify_candidate_mounts
from stateful_storage_fit.classify_processes import classify_processes
from stateful_storage_fit.config import DEFAULT_THRESHOLDS
from stateful_storage_fit.fit_rules import build_fit_result
from stateful_storage_fit.parse_df import parse_df_text
from stateful_storage_fit.parse_fstab import parse_fstab_text
from stateful_storage_fit.parse_iostat import parse_iostat_text
from stateful_storage_fit.parse_mount import parse_mount_text
from stateful_storage_fit.parse_processes import parse_processes_text
from stateful_storage_fit.storage_profile import parse_storage_profile_text


PROFILE = """
storage_classes:
  - name: standard-rwo
    access_modes: [ReadWriteOnce]
    volume_modes: [Filesystem]
    storage_kind: block
    performance_tier: standard
    max_size_gib: 2048
    supports_expansion: true
    supports_snapshots: true
  - name: fast-rwo
    access_modes: [ReadWriteOnce]
    volume_modes: [Filesystem]
    storage_kind: block
    performance_tier: fast
    max_size_gib: 4096
    supports_expansion: true
    supports_snapshots: true
  - name: shared-rwx
    access_modes: [ReadWriteMany]
    volume_modes: [Filesystem]
    storage_kind: file
    performance_tier: standard
    max_size_gib: 8192
  - name: raw-block-rwo
    access_modes: [ReadWriteOnce]
    volume_modes: [Block]
    storage_kind: block
    performance_tier: fast
    max_size_gib: 4096
performance_tiers:
  standard: 1
  fast: 2
  low_latency: 3
"""

STANDARD_ONLY_PROFILE = """
storage_classes:
  - name: standard-rwo
    access_modes: [ReadWriteOnce]
    volume_modes: [Filesystem]
    storage_kind: block
    performance_tier: standard
    max_size_gib: 2048
performance_tiers:
  standard: 1
  fast: 2
  low_latency: 3
"""


DF_DATA = """Filesystem Type 1B-blocks Used Available Use% Mounted on
/dev/sda1 ext4 107374182400 21474836480 85899345920 20% /
/dev/sdb1 xfs 214748364800 107374182400 107374182400 50% /data
"""

MOUNT_DATA = """/dev/sda1 on / type ext4 (rw,relatime)
/dev/sdb1 on /data type xfs (rw,relatime)
"""

FSTAB_DATA = """/dev/sda1 / ext4 defaults 0 1
/dev/sdb1 /data xfs defaults 0 2
"""

IOSTAT_LOW = """Device r/s w/s rkB/s wkB/s await aqu-sz %util
sda 0.1 0.2 4 8 0.5 0.01 1.0
sdb 1.0 2.0 64 128 2.0 0.05 10.0

Device r/s w/s rkB/s wkB/s await aqu-sz %util
sda 0.1 0.2 4 8 0.6 0.01 1.0
sdb 1.0 2.0 64 128 3.0 0.05 15.0
"""

IOSTAT_HIGH = """Device r/s w/s rkB/s wkB/s await aqu-sz %util
sdb 1 2 64 128 5.0 0.1 10.0

Device r/s w/s rkB/s wkB/s await aqu-sz %util
sdb 4 10 128 1024 24.8 2.5 72.0
"""

PS_DB = "100 postgres /usr/bin/postgres -D /data/db\n"
PS_FILE_SERVER = "200 smbd /usr/sbin/smbd --foreground\n"


def analyze(
    *,
    df_text: str | None = DF_DATA,
    mount_text: str | None = MOUNT_DATA,
    fstab_text: str | None = FSTAB_DATA,
    iostat_text: str | None = IOSTAT_LOW,
    ps_text: str | None = "",
    profile_text: str | None = PROFILE,
    config: dict | None = None,
):
    thresholds = dict(DEFAULT_THRESHOLDS)
    if config:
        thresholds.update(config)

    missing = []
    parse_warnings = []
    df_entries = []
    mount_entries = []
    fstab_entries = []
    iostat_samples = {}
    iostat_meta = {"max_observed_await_ms": None, "max_observed_util_pct": None}
    processes = []

    if df_text is None:
        missing.append("df")
    else:
        df_entries, warnings = parse_df_text(df_text)
        parse_warnings.extend(warnings)
    if mount_text is None:
        missing.append("mount")
    else:
        mount_entries, warnings = parse_mount_text(mount_text)
        parse_warnings.extend(warnings)
    if fstab_text is None:
        missing.append("fstab")
    else:
        fstab_entries, warnings = parse_fstab_text(fstab_text)
        parse_warnings.extend(warnings)
    if iostat_text is None:
        missing.append("iostat")
    else:
        iostat_samples, warnings, iostat_meta = parse_iostat_text(iostat_text)
        parse_warnings.extend(warnings)
    if ps_text is None:
        missing.append("ps")
    else:
        processes, warnings = parse_processes_text(ps_text)
        parse_warnings.extend(warnings)

    profile = parse_storage_profile_text(profile_text) if profile_text else None
    process_info = classify_processes(processes)
    candidates, mount_warnings, uncertain = classify_candidate_mounts(
        df_entries, mount_entries, fstab_entries, iostat_samples, thresholds, []
    )
    parse_warnings.extend(mount_warnings)
    non_candidate_network = any_non_candidate_network_fs(candidates, mount_entries, fstab_entries)
    return build_fit_result(
        candidates=candidates,
        mounts_network_elsewhere=non_candidate_network,
        process_info=process_info,
        profile=profile,
        profile_error=None,
        iostat_samples=iostat_samples,
        iostat_meta=iostat_meta,
        missing_data=missing,
        parse_warnings=parse_warnings,
        uncertain_mapping=uncertain,
        config=thresholds,
    ), candidates

