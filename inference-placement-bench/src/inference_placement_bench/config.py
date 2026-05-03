from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "default_measured_requests": 50,
    "default_warmup_requests": 5,
    "default_concurrency": 1,
    "default_request_timeout_seconds": 60,
    "minimum_successful_requests_high_confidence": 50,
    "minimum_successful_requests_medium_confidence": 20,
    "minimum_successful_requests_review": 5,
    "latency_miss_review_margin_pct": 10,
    "throughput_miss_review_margin_pct": 10,
    "error_rate_near_threshold_pct": 0.5,
    "token_estimate_chars_per_token": 4,
    "percentile_method": "nearest_rank",
    "include_failures_in_latency": False,
    "allow_commit_amortization": False,
    "preserve_location_labels": False,
    "http": {
        "require_https": True,
        "allow_http_local_lab": True,
        "user_agent": "inference-placement-bench/0.1",
        "max_response_bytes": 10485760,
    },
    "safety": {
        "allow_sensitive_prompt_patterns": False,
        "log_full_prompts_by_default": False,
        "log_full_responses_by_default": False,
    },
}


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | None = None) -> dict[str, Any]:
    if not path:
        return deepcopy(DEFAULT_CONFIG)
    loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError("config file must contain a mapping")
    return deep_merge(DEFAULT_CONFIG, loaded)
