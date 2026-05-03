from __future__ import annotations

from pathlib import Path

from .config import load_yaml_file
from .models import BucketConfig


def load_bucket_config(path: str | Path | None) -> BucketConfig:
    return BucketConfig(**load_yaml_file(path))


def bucket_config_features(config: BucketConfig) -> list[str]:
    features: set[str] = set()
    if config.versioning:
        features.add("VERSIONING")
    if config.object_lock:
        features.add("OBJECT_LOCK")
    if config.cors:
        features.add("CORS")
    if config.lifecycle:
        features.add("LIFECYCLE")
    if config.ownership_controls:
        features.add("OWNERSHIP_CONTROLS")
    if config.requester_pays is not None:
        features.add("REQUESTER_PAYS")
    if config.encryption:
        features.add("ENCRYPTION_CONFIG")
    if config.replication:
        features.add("REPLICATION")
    if config.event_notifications:
        features.add("EVENT_NOTIFICATIONS")
    if config.policy_context:
        features.add("POLICY_CONTEXT")
    return sorted(features)
