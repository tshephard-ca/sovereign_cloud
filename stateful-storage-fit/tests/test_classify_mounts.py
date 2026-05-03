from stateful_storage_fit.classify_mounts import classify_candidate_mounts
from stateful_storage_fit.config import DEFAULT_THRESHOLDS
from stateful_storage_fit.parse_df import parse_df_text
from stateful_storage_fit.parse_fstab import parse_fstab_text
from stateful_storage_fit.parse_iostat import parse_iostat_text
from stateful_storage_fit.parse_mount import parse_mount_text

from tests.helpers import IOSTAT_LOW, analyze


def test_detects_nfs_data_mount_and_requires_rwx():
    result, _ = analyze(
        df_text="""Filesystem Type 1B-blocks Used Available Use% Mounted on
server:/export nfs4 214748364800 107374182400 107374182400 50% /srv/content
""",
        mount_text="server:/export on /srv/content type nfs4 (rw,relatime)\n",
        fstab_text="server:/export /srv/content nfs4 defaults 0 0\n",
    )
    assert result.required_access_mode == "ReadWriteMany"
    assert result.preferred_storage_kind == "file"
    assert "SHARED_FS_DETECTED" in result.reason_codes


def test_detects_cifs_data_mount_and_requires_rwx():
    result, _ = analyze(
        df_text="""Filesystem Type 1B-blocks Used Available Use% Mounted on
//server/share cifs 214748364800 107374182400 107374182400 50% /srv/share
""",
        mount_text="//server/share on /srv/share type cifs (rw,relatime)\n",
        fstab_text="//server/share /srv/share cifs defaults 0 0\n",
    )
    assert result.required_access_mode == "ReadWriteMany"
    assert "RWX_REQUIRED" in result.reason_codes


def test_maps_dev_sda1_to_iostat_device_sda():
    df_entries, _ = parse_df_text(
        """Filesystem Type 1B-blocks Used Available Use% Mounted on
/dev/sda1 xfs 214748364800 107374182400 107374182400 50% /data
"""
    )
    mounts, _ = parse_mount_text("/dev/sda1 on /data type xfs (rw,relatime)\n")
    fstab, _ = parse_fstab_text("")
    samples, _, _ = parse_iostat_text(IOSTAT_LOW)
    candidates, _, uncertain = classify_candidate_mounts(df_entries, mounts, fstab, samples, DEFAULT_THRESHOLDS)
    assert not uncertain
    assert candidates[0].device_from_iostat == "sda"


def test_marks_uncertain_device_mapping_when_needed():
    result, _ = analyze(
        df_text="""Filesystem Type 1B-blocks Used Available Use% Mounted on
/dev/mapper/vg-data xfs 214748364800 107374182400 107374182400 50% /data
""",
        mount_text="/dev/mapper/vg-data on /data type xfs (rw,relatime)\n",
    )
    assert "IOSTAT_DEVICE_MAPPING_UNCERTAIN" in result.warnings

