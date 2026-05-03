from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import StorageClassProfile, StorageProfile


VALID_STORAGE_KINDS = {"block", "file", "local", "unknown"}


class StorageProfileError(ValueError):
    pass


def parse_storage_profile_text(text: str) -> StorageProfile:
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise StorageProfileError(f"storage profile YAML parse failed: {exc}") from exc

    if not isinstance(data, dict):
        raise StorageProfileError("storage profile must be a YAML mapping")
    classes_data = data.get("storage_classes")
    if not isinstance(classes_data, list) or not classes_data:
        raise StorageProfileError("storage_classes is required and must contain at least one class")
    tiers = data.get("performance_tiers")
    if not isinstance(tiers, dict) or not tiers:
        raise StorageProfileError("performance_tiers is required and must be a mapping")

    storage_classes: list[StorageClassProfile] = []
    for index, raw_class in enumerate(classes_data):
        if not isinstance(raw_class, dict):
            raise StorageProfileError(f"storage_classes[{index}] must be a mapping")
        raw = dict(raw_class)
        raw.setdefault("supports_expansion", False)
        raw.setdefault("supports_snapshots", False)
        for field in ("name", "access_modes", "volume_modes", "storage_kind", "performance_tier"):
            if field not in raw or raw[field] in (None, "", []):
                raise StorageProfileError(f"storage_classes[{index}].{field} is required")
        if raw["storage_kind"] not in VALID_STORAGE_KINDS:
            raise StorageProfileError(
                f"storage_classes[{index}].storage_kind must be one of: {', '.join(sorted(VALID_STORAGE_KINDS))}"
            )
        if raw["performance_tier"] not in tiers:
            raise StorageProfileError(
                f"storage_classes[{index}].performance_tier must exist in performance_tiers"
            )
        try:
            storage_classes.append(StorageClassProfile(**raw))
        except ValidationError as exc:
            raise StorageProfileError(f"storage_classes[{index}] validation failed: {exc}") from exc

    normalized_tiers: dict[str, int] = {}
    for name, rank in tiers.items():
        try:
            normalized_tiers[str(name)] = int(rank)
        except (TypeError, ValueError) as exc:
            raise StorageProfileError(f"performance_tiers.{name} must be an integer rank") from exc

    return StorageProfile(storage_classes=storage_classes, performance_tiers=normalized_tiers)


def parse_storage_profile_file(path: Path) -> StorageProfile:
    return parse_storage_profile_text(path.read_text(encoding="utf-8", errors="replace"))


def profile_fingerprint(profile: StorageProfile) -> dict[str, Any]:
    return {
        "storage_class_count": len(profile.storage_classes),
        "performance_tiers": sorted(profile.performance_tiers),
    }

