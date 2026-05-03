from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "required_window_days": 7,
    "default_bucket_minutes": 5,
    "minimum_coverage_pct": 85,
    "sustained_window_minutes": 60,
    "burst_window_minutes": 5,
    "burst_percentile": 99,
    "sustained_percentile": 95,
    "min_power_variation_kw_for_thermal_model": 2.0,
    "min_power_variation_pct_for_thermal_model": 10,
    "min_temp_variation_c_for_thermal_model": 0.5,
    "min_thermal_model_r2": 0.20,
    "min_positive_temp_slope_c_per_kw": 0.02,
    "max_default_thermal_extrapolation_kw": 5.0,
    "default_power_headroom_pct": 10,
    "default_min_power_headroom_kw": 1.0,
    "default_temp_headroom_c": 2.0,
    "high_trip_risk_margin_kw": 1.0,
    "medium_trip_risk_margin_kw": 2.0,
    "high_thermal_risk_margin_c": 1.0,
    "medium_thermal_risk_margin_c": 2.0,
    "plausible_min_temp_c": 0,
    "plausible_max_temp_c": 60,
    "feed_imbalance_warning_pct": 20,
    "feed_imbalance_critical_pct": 35,
    "redaction_hash_length": 12,
    "hotspot_top_bottom_delta_c": 4.0,
    "long_gap_minutes": 60,
    "allow_all_zero_power": False,
}


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


BUILTIN_POLICY_PACKS = {
    "conservative-air-cooled": {
        "minimum_coverage_pct": 90,
        "default_power_headroom_pct": 12,
        "default_temp_headroom_c": 2.5,
        "medium_thermal_risk_margin_c": 2.5,
    },
    "sales-prequalification": {
        "minimum_coverage_pct": 85,
        "default_power_headroom_pct": 15,
        "default_temp_headroom_c": 3.0,
        "medium_trip_risk_margin_kw": 3.0,
    },
    "operations-review": {
        "minimum_coverage_pct": 80,
        "default_power_headroom_pct": 10,
        "default_temp_headroom_c": 2.0,
    },
}


def load_policy_pack(policy_pack: str | Path | None) -> dict[str, Any]:
    if policy_pack is None:
        return {}
    name = str(policy_pack)
    if name in BUILTIN_POLICY_PACKS:
        return deepcopy(BUILTIN_POLICY_PACKS[name])
    path = Path(policy_pack)
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError("policy pack must be a YAML mapping")
    return loaded


def load_config(path: str | Path | None = None, policy_pack: str | Path | None = None) -> dict[str, Any]:
    config = deepcopy(DEFAULT_CONFIG)
    config = deep_merge(config, load_policy_pack(policy_pack))
    if path is None:
        return config
    with Path(path).open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError("threshold config must be a YAML mapping")
    return deep_merge(config, loaded)
