from stateful_storage_fit.parse_df import parse_df_text


def test_parses_df_pt_b1():
    entries, warnings = parse_df_text(
        """Filesystem Type 1B-blocks Used Available Use% Mounted on
/dev/sdb1 xfs 214748364800 107374182400 107374182400 50% /data
"""
    )
    assert not warnings
    assert entries[0].fs_type == "xfs"
    assert entries[0].used_bytes == 107374182400
    assert entries[0].mount_path == "/data"


def test_parses_df_h():
    entries, warnings = parse_df_text(
        """Filesystem Size Used Avail Use% Mounted on
/dev/sdb1 200G 100G 100G 50% /data
"""
    )
    assert not warnings
    assert entries[0].used_bytes == 100 * 1024**3
    assert entries[0].capacity_pct == 50

