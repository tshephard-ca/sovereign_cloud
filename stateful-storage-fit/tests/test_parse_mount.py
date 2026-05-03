from stateful_storage_fit.parse_mount import parse_mount_text


def test_parses_mount_output_with_ext4_xfs_data_mount():
    entries, warnings = parse_mount_text(
        """/dev/sda1 on / type ext4 (rw,relatime)
/dev/sdb1 on /data type xfs (rw,relatime)
"""
    )
    assert not warnings
    assert entries[1].source == "/dev/sdb1"
    assert entries[1].mount_path == "/data"
    assert entries[1].fs_type == "xfs"

