"""Threshold configuration."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from estate_triage.models import TriageError


class Thresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_n: int = Field(default=25, ge=1)
    recent_backup_days: int = Field(default=14, ge=0)
    stale_backup_days: int = Field(default=60, ge=0)
    high_cpu_count: int = Field(default=8, ge=1)
    high_memory_mib: int = Field(default=32768, ge=1)
    small_workload_mib: int = Field(default=204800, ge=1)
    large_backup_mib: int = Field(default=1048576, ge=1)
    low_change_rate_pct: float = Field(default=1.0, ge=0)
    high_backup_to_used_ratio: float = Field(default=3.0, ge=0)
    many_restore_points: int = Field(default=30, ge=0)
    idle_cpu_pct: float = Field(default=5, ge=0)
    low_memory_usage_pct: float = Field(default=30, ge=0)


DEFAULT_THRESHOLDS = Thresholds()


def load_thresholds(config_path: Path | None = None) -> Thresholds:
    if config_path is None:
        return DEFAULT_THRESHOLDS.model_copy()

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise TriageError(f"Could not read config file {config_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise TriageError(f"Could not parse YAML config {config_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise TriageError("Config file must contain a YAML mapping of threshold names.")

    try:
        return Thresholds(**{**DEFAULT_THRESHOLDS.model_dump(), **raw})
    except Exception as exc:  # pydantic raises several validation subclasses.
        raise TriageError(f"Invalid config values in {config_path}: {exc}") from exc
