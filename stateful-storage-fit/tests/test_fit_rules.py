from tests.helpers import IOSTAT_HIGH, PROFILE, PS_DB, PS_FILE_SERVER, STANDARD_ONLY_PROFILE, analyze


def test_detects_database_process_and_prefers_block_storage():
    result, _ = analyze(ps_text=PS_DB)
    assert result.preferred_storage_kind == "block"
    assert "DB_PROCESS_DETECTED" in result.reason_codes
    assert "BLOCK_STORAGE_PREFERRED" in result.reason_codes


def test_detects_file_server_process_and_returns_review():
    result, _ = analyze(ps_text=PS_FILE_SERVER)
    assert result.fit_status == "REVIEW"
    assert "FILE_SERVER_PROCESS_DETECTED" in result.reason_codes


def test_handles_missing_iostat_as_review_not_fail():
    result, _ = analyze(iostat_text=None)
    assert result.fit_status == "REVIEW"
    assert "iostat" in result.missing_data
    assert "IOSTAT_MISSING" in result.reason_codes


def test_handles_missing_process_list_as_review_not_fail():
    result, _ = analyze(ps_text=None)
    assert result.fit_status == "REVIEW"
    assert "ps" in result.missing_data
    assert "PROCESS_LIST_MISSING" in result.reason_codes


def test_computes_storage_request_gib_with_headroom():
    result, _ = analyze()
    assert result.storage_request_gib == 125


def test_fails_when_required_size_exceeds_all_matching_profiles():
    huge_df = """Filesystem Type 1B-blocks Used Available Use% Mounted on
/dev/sdb1 xfs 5368709120000 4294967296000 1073741824000 80% /data
"""
    result, _ = analyze(df_text=huge_df, profile_text=STANDARD_ONLY_PROFILE)
    assert result.fit_status == "FAIL"
    assert "CAPACITY_EXCEEDS_AVAILABLE_PROFILE" in result.blockers


def test_passes_when_standard_rwo_profile_matches():
    result, _ = analyze(profile_text=STANDARD_ONLY_PROFILE)
    assert result.fit_status == "PASS"
    assert result.recommended_storage_class == "standard-rwo"


def test_reviews_when_db_high_latency_but_fast_profile_exists():
    result, _ = analyze(ps_text=PS_DB, iostat_text=IOSTAT_HIGH, profile_text=PROFILE)
    assert result.fit_status == "REVIEW"
    assert result.recommended_storage_class == "fast-rwo"
    assert "FAST_STORAGE_RECOMMENDED" in result.reason_codes


def test_fails_when_shared_filesystem_requires_rwx_and_no_rwx_profile_exists():
    result, _ = analyze(
        df_text="""Filesystem Type 1B-blocks Used Available Use% Mounted on
server:/export nfs4 214748364800 107374182400 107374182400 50% /srv/content
""",
        mount_text="server:/export on /srv/content type nfs4 (rw,relatime)\n",
        fstab_text="server:/export /srv/content nfs4 defaults 0 0\n",
        profile_text=STANDARD_ONLY_PROFILE,
    )
    assert result.fit_status == "FAIL"
    assert "SHARED_FILESYSTEM_REQUIRED_NO_RWX_PROFILE" in result.blockers


def test_output_json_shape_contains_required_fields():
    result, _ = analyze(ps_text=PS_DB)
    assert result.fit_status
    assert result.recommended_storage_class
    assert isinstance(result.reason_codes, list)
    assert isinstance(result.blockers, list)
    assert isinstance(result.warnings, list)
    assert "candidate_data_mounts" in result.evidence


def test_ranking_of_matched_storage_classes_is_deterministic():
    profile = """
storage_classes:
  - name: z-fast
    access_modes: [ReadWriteOnce]
    volume_modes: [Filesystem]
    storage_kind: block
    performance_tier: fast
    max_size_gib: 4096
  - name: a-standard
    access_modes: [ReadWriteOnce]
    volume_modes: [Filesystem]
    storage_kind: block
    performance_tier: standard
    max_size_gib: 4096
  - name: b-standard
    access_modes: [ReadWriteOnce]
    volume_modes: [Filesystem]
    storage_kind: block
    performance_tier: standard
    max_size_gib: 4096
performance_tiers:
  standard: 1
  fast: 2
"""
    result, _ = analyze(profile_text=profile)
    assert result.matched_storage_classes == ["a-standard", "b-standard", "z-fast"]
    assert result.recommended_storage_class == "a-standard"

