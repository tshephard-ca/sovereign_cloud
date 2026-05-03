from datetime import timezone

from estate_triage.normalize import normalize_name, parse_datetime, parse_float, parse_mib


def test_normalized_name_trims_lowercases_and_collapses_spaces():
    assert normalize_name("  App   Server  01 ") == "app server 01"


def test_parse_mib_supports_suffixes_and_commas():
    warnings: list[str] = []
    assert parse_mib("1,024", field="storage", row_number=2, warnings=warnings) == 1024
    assert parse_mib("2 GiB", field="storage", row_number=2, warnings=warnings) == 2048
    assert parse_mib("1.5 TiB", field="storage", row_number=2, warnings=warnings) == 1572864
    assert warnings == []


def test_parse_numbers_support_decimal_comma_when_unambiguous():
    warnings: list[str] = []
    assert parse_float("5,5%", field="cpu_usage_pct", row_number=2, warnings=warnings) == 5.5
    assert parse_mib("512,5 GiB", field="storage", row_number=2, warnings=warnings) == 524800
    assert parse_mib("1.024,5 MiB", field="storage", row_number=2, warnings=warnings) == 1024.5
    assert warnings == []


def test_ambiguous_slash_date_is_ignored_with_warning():
    warnings: list[str] = []
    parsed = parse_datetime(
        "04/05/2026",
        field="latest_restore_point_utc",
        row_number=2,
        warnings=warnings,
    )
    assert parsed is None
    assert "ambiguous date" in warnings[0]


def test_unambiguous_dates_are_utc():
    warnings: list[str] = []
    parsed = parse_datetime(
        "13/05/2026",
        field="latest_restore_point_utc",
        row_number=2,
        warnings=warnings,
    )
    assert parsed is not None
    assert parsed.tzinfo == timezone.utc
    assert parsed.month == 5
    assert parsed.day == 13


def test_unambiguous_dotted_dates_are_utc():
    warnings: list[str] = []
    parsed = parse_datetime(
        "31.03.2026",
        field="latest_restore_point_utc",
        row_number=2,
        warnings=warnings,
    )
    assert parsed is not None
    assert parsed.tzinfo == timezone.utc
    assert parsed.month == 3
    assert parsed.day == 31
    assert warnings == []
