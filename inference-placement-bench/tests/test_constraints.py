from __future__ import annotations

from inference_placement_bench.constraints import declared_location_reason_codes, load_constraints
from inference_placement_bench.models import DeclaredLocation

from conftest import make_constraints


def test_parses_valid_constraints_file(project_root):
    constraints = load_constraints(str(project_root / "examples/constraints.yml"))
    assert constraints.constraint_id == "chat_support_ca_low_latency"


def test_validates_declared_location_pass():
    ok, codes = declared_location_reason_codes(
        DeclaredLocation(country="CA", region="region-a", data_zone="ca-zone-1", operator_control="local"),
        make_constraints(),
    )
    assert ok is True
    assert "DECLARED_LOCATION_ALLOWED" in codes


def test_validates_declared_location_fail():
    ok, codes = declared_location_reason_codes(
        DeclaredLocation(country="ZZ", region="region-z", data_zone="zone-z", operator_control="local"),
        make_constraints(),
    )
    assert ok is False
    assert "DECLARED_LOCATION_NOT_ALLOWED" in codes


def test_validates_missing_declared_location_when_required():
    ok, codes = declared_location_reason_codes(None, make_constraints())
    assert ok is False
    assert codes == ["DECLARED_LOCATION_MISSING"]
