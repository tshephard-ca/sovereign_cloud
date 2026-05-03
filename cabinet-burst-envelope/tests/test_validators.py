from __future__ import annotations

import pytest

from cabinet_burst_envelope.validators import load_and_validate_inputs

from .conftest import base_profile, generated_power_rows, generated_temperature_rows, write_power_rows, write_profile, write_temperature_rows


def test_strict_fails_when_cabinet_ids_do_not_match(tmp_path, default_config):
    profile = write_profile(tmp_path, base_profile("cab-profile"))
    power = write_power_rows(tmp_path, generated_power_rows(cabinet_id="cab-power", count=1))
    temp = write_temperature_rows(tmp_path, generated_temperature_rows(cabinet_id="cab-temp", count=1))
    with pytest.raises(ValueError, match="cabinet IDs do not match"):
        load_and_validate_inputs(power, temp, profile, default_config, strict=True)


def test_non_strict_filters_to_profile_cabinet(tmp_path, default_config):
    profile = write_profile(tmp_path, base_profile("cab-keep"))
    power_rows = generated_power_rows(cabinet_id="cab-keep", count=1) + generated_power_rows(cabinet_id="cab-other", count=1)
    temp_rows = generated_temperature_rows(cabinet_id="cab-keep", count=1) + generated_temperature_rows(cabinet_id="cab-other", count=1)
    loaded = load_and_validate_inputs(
        write_power_rows(tmp_path, power_rows),
        write_temperature_rows(tmp_path, temp_rows),
        profile,
        default_config,
        strict=False,
    )
    assert loaded.cabinet_id == "cab-keep"
    assert {row.cabinet_id for row in loaded.power_rows} == {"cab-keep"}
    assert "MULTIPLE_CABINETS_IN_INPUT" in loaded.warnings


def test_all_zero_power_readings_are_flagged(tmp_path, default_config):
    profile = write_profile(tmp_path, base_profile("cab-zero"))
    power_rows = generated_power_rows(cabinet_id="cab-zero", count=2, scope="total_cabinet", base_kw=0, variation_kw=0)
    for row in power_rows:
        row["reading_kw"] = 0
    temp_rows = generated_temperature_rows(cabinet_id="cab-zero", count=2)
    loaded = load_and_validate_inputs(
        write_power_rows(tmp_path, power_rows),
        write_temperature_rows(tmp_path, temp_rows),
        profile,
        default_config,
        strict=False,
    )
    assert "ALL_ZERO_POWER_READINGS" in loaded.warnings
