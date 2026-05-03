from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_path_purpose(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"paths": []}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("path purpose file must be a YAML mapping")
    paths = data.get("paths", [])
    if not isinstance(paths, list):
        raise ValueError("path purpose file must contain paths list")
    normalized = []
    for index, item in enumerate(paths):
        if not isinstance(item, dict):
            raise ValueError(f"paths[{index}] must be a mapping")
        if not item.get("path"):
            raise ValueError(f"paths[{index}].path is required")
        normalized.append(
            {
                "path": str(item["path"]),
                "purpose": str(item.get("purpose", "unknown")),
                "read_write_pattern": str(item.get("read_write_pattern", "unknown")),
                "writer_topology": str(item.get("writer_topology", "unknown")),
                "owner_confidence": str(item.get("owner_confidence", "LOW")),
                "notes": item.get("notes", ""),
            }
        )
    return {"paths": normalized}


def build_app_metadata(
    *,
    app_name: str | None = None,
    workload_family: str | None = None,
    path_purpose_file: Path | None = None,
) -> dict[str, Any]:
    path_purpose = load_path_purpose(path_purpose_file)
    return {
        "app_name": app_name,
        "workload_family": workload_family,
        "path_purpose": path_purpose,
        "declared_data_paths": [item["path"] for item in path_purpose.get("paths", [])],
    }

