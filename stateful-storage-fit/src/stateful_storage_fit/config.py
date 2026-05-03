from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_THRESHOLDS: dict[str, Any] = {
    "data_mount_min_used_gib": 1,
    "storage_headroom_pct": 25,
    "storage_min_extra_gib": 10,
    "high_capacity_used_pct": 85,
    "critical_capacity_used_pct": 95,
    "latency_medium_await_ms": 10,
    "latency_high_await_ms": 20,
    "util_medium_pct": 60,
    "util_high_pct": 80,
    "queue_medium_depth": 2,
    "queue_high_depth": 5,
    "db_requires_fast_if_latency_high": True,
    "db_prefers_block_storage": True,
    "shared_fs_requires_rwx": True,
    "process_args_max_chars": 120,
}


def load_thresholds(path: Path | None = None) -> dict[str, Any]:
    config = dict(DEFAULT_THRESHOLDS)
    if path is None:
        return config
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("threshold config must be a YAML mapping")
    config.update(data)
    return config

