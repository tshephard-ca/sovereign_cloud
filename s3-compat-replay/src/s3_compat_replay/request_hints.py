from __future__ import annotations

from pathlib import Path

from .config import load_yaml_file
from .models import RequestHints


def load_request_hints(path: str | Path | None) -> RequestHints:
    return RequestHints(**load_yaml_file(path))


def request_hint_features(hints: RequestHints) -> list[str]:
    features: set[str] = set()
    if hints.presigned.get("observed"):
        features.add("PRESIGNED_OBSERVED")
    if hints.cors:
        features.add("CORS")
    if hints.metadata_headers:
        features.add("METADATA_HEADERS")
    if hints.object_tags:
        features.add("OBJECT_TAGGING")
    if hints.content_types:
        features.add("CONTENT_TYPES")
    if hints.conditional_requests:
        features.add("CONDITIONAL_REQUESTS")
    if hints.range_gets.get("observed"):
        features.add("RANGE_GETS")
    if hints.object_lock:
        features.add("OBJECT_LOCK")
    if hints.body_classes:
        features.add("BODY_CLASSES")
    if hints.presigned_expiration_buckets:
        features.add("PRESIGNED_EXPIRATION_BUCKETS")
    if hints.object_size_distribution:
        features.add("OBJECT_SIZE_DISTRIBUTION")
    if hints.requester_pays:
        features.add("REQUESTER_PAYS_TRAFFIC")
    if hints.pagination:
        features.add("PAGINATION_TOKENS")
    if hints.consistency_expectations:
        features.add("CONSISTENCY_EXPECTATIONS")
    return sorted(features)
