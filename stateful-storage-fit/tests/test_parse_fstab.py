from stateful_storage_fit.parse_fstab import parse_fstab_text


def test_parses_fstab_comments_and_blank_lines():
    entries, warnings = parse_fstab_text(
        """
# root
/dev/sda1 / ext4 defaults 0 1

/dev/sdb1 /data xfs defaults,noatime 0 2 # data
"""
    )
    assert not warnings
    assert len(entries) == 2
    assert entries[1].mount_path == "/data"
    assert entries[1].options == ["defaults", "noatime"]

