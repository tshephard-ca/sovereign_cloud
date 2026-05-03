import pytest

from dr_prereq_lint.backup_inventory import parse_backup_inventory
from dr_prereq_lint.recovery_set import build_recovery_set


def test_parses_backup_inventory_with_required_columns(tmp_path, csv_writer):
    path = csv_writer(tmp_path / "inventory.csv", [{"workload_name": "app01"}])
    result = parse_backup_inventory(path)
    assert result.rows[0].workload_name == "app01"
    assert result.protected_systems[0].short_name == "app01"


def test_parses_backup_inventory_with_alias_columns(tmp_path, csv_writer):
    path = csv_writer(
        tmp_path / "inventory.csv",
        [{"server_name": "app01", "dns_name": "APP01.EXAMPLE.INTERNAL.", "guest_ip": "10.0.0.1"}],
    )
    result = parse_backup_inventory(path)
    assert result.rows[0].fqdn == "app01.example.internal"
    assert result.rows[0].ip_addresses == ["10.0.0.1"]


def test_inferrs_recovery_set_when_include_column_missing_and_warns(tmp_path, csv_writer):
    path = csv_writer(
        tmp_path / "inventory.csv",
        [{"workload_name": "app01", "protected": "true", "recovery_set": "dr-test-001"}],
    )
    parsed = parse_backup_inventory(path)
    recovery = build_recovery_set(parsed.rows, recovery_set_name="dr-test-001")
    assert len(recovery.systems) == 1
    assert "RECOVERY_SET_SCOPE_ASSUMED" in recovery.warnings


def test_strict_mode_fails_when_no_workload_name_column_exists(tmp_path, csv_writer):
    path = csv_writer(tmp_path / "inventory.csv", [{"not_a_name": "app01"}])
    with pytest.raises(ValueError, match="workload_name"):
        parse_backup_inventory(path, strict=True)
