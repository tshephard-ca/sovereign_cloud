from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ExtractionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label_scan_left_chars: int = 40
    generated_hash_length: int = 12
    max_response_fields_without_field_map: int = 20
    detect_subfile_min_repeated_rows: int = 4
    detect_subfile_similarity_pct: int = 75
    volatile_date_patterns: bool = True
    volatile_time_patterns: bool = True
    redact_sensitive_by_default: bool = True


DEFAULT_CONFIG = ExtractionConfig()


def load_config(path: str | Path | None = None) -> ExtractionConfig:
    if path is None:
        return DEFAULT_CONFIG.model_copy()
    data = yaml.safe_load(Path(path).read_text()) or {}
    merged: dict[str, Any] = DEFAULT_CONFIG.model_dump()
    merged.update(data)
    return ExtractionConfig(**merged)
