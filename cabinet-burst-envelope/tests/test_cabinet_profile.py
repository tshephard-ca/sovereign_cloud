from __future__ import annotations

import pytest

from cabinet_burst_envelope.cabinet_profile import load_cabinet_profile

from .conftest import base_profile, write_profile


def test_parses_cabinet_profile_yaml(tmp_path):
    path = write_profile(tmp_path, base_profile("cab-profile"))
    profile, result = load_cabinet_profile(path)
    assert profile is not None
    assert profile.cabinet_id == "cab-profile"
    assert profile.electrical.usable_sustained_kw == 24.0
    assert "CABINET_PROFILE_PRESENT" in result.reason_codes


def test_strict_fails_when_cabinet_profile_missing(tmp_path):
    with pytest.raises(ValueError, match="cabinet profile is required"):
        load_cabinet_profile(tmp_path / "missing.yml", strict=True)


def test_strict_fails_when_profile_limits_conflict(tmp_path):
    profile = base_profile("cab-invalid")
    profile["electrical"]["usable_burst_kw"] = 20.0
    profile["electrical"]["trip_risk_kw"] = 19.0
    profile["thermal"]["inlet_critical_c"] = 25.0
    path = write_profile(tmp_path, profile)
    with pytest.raises(ValueError, match="invalid cabinet profile contract"):
        load_cabinet_profile(path, strict=True)


def test_non_strict_profile_conflicts_emit_profile_invalid(tmp_path):
    profile = base_profile("cab-invalid")
    profile["electrical"]["usable_burst_kw"] = 20.0
    path = write_profile(tmp_path, profile)
    parsed, result = load_cabinet_profile(path, strict=False)
    assert parsed is not None
    assert "BURST_LIMIT_BELOW_SUSTAINED_LIMIT" in result.reason_codes
    assert "PROFILE_INVALID" in result.missing_data
