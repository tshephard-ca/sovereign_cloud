from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

from .engine import analyze_paths
from .models import model_to_dict


def _resolve(base: Path, value: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    return path if path.is_absolute() else base / path


def analyze_portfolio(inventory_path: Path) -> dict:
    data = yaml.safe_load(inventory_path.read_text(encoding="utf-8")) or {}
    workloads = data.get("workloads", [])
    if not isinstance(workloads, list):
        raise ValueError("portfolio inventory must contain workloads list")
    base = inventory_path.parent
    status_counts: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    demand_counts: Counter[str] = Counter()
    missing_counts: Counter[str] = Counter()
    results = []
    for item in workloads:
        if not isinstance(item, dict):
            continue
        workload_id = item.get("id") or item.get("name") or f"workload_{len(results) + 1}"
        bundle = analyze_paths(
            df=_resolve(base, item.get("df")),
            mount=_resolve(base, item.get("mount")),
            fstab=_resolve(base, item.get("fstab")),
            iostat=_resolve(base, item.get("iostat")),
            ps=_resolve(base, item.get("ps")),
            storage_profile_path=_resolve(base, item.get("storage_profile")),
            config=_resolve(base, item.get("config")),
            policy_pack_path=_resolve(base, item.get("policy_pack")),
            data_paths=item.get("data_paths") or [],
            strict=False,
        )
        result = bundle.result
        status_counts[result.fit_status] += 1
        blocker_counts.update(result.blockers)
        reason_counts.update(result.reason_codes)
        missing_counts.update(result.missing_data)
        if result.required_access_mode == "ReadWriteMany":
            demand_counts["rwx"] += 1
        if result.required_access_mode == "ReadWriteOnce":
            demand_counts["rwo"] += 1
        if result.preferred_storage_kind == "block":
            demand_counts["block"] += 1
        if result.preferred_storage_kind == "file":
            demand_counts["file"] += 1
        if "FAST_STORAGE_RECOMMENDED" in result.reason_codes:
            demand_counts["fast_block"] += 1
        if "RAW_BLOCK_HINT" in result.reason_codes:
            demand_counts["raw_block_hint"] += 1
        if "CAPACITY_EXCEEDS_AVAILABLE_PROFILE" in result.reason_codes:
            demand_counts["capacity_exceeds_profile"] += 1
        results.append(
            {
                "id": workload_id,
                "fit_status": result.fit_status,
                "recommended_storage_class": result.recommended_storage_class,
                "required_access_mode": result.required_access_mode,
                "required_volume_mode": result.required_volume_mode,
                "preferred_storage_kind": result.preferred_storage_kind,
                "storage_request_gib": result.storage_request_gib,
                "blockers": result.blockers,
                "warnings": result.warnings,
                "reason_codes": result.reason_codes,
                "missing_data": result.missing_data,
            }
        )
    return {
        "schema_version": "1.0",
        "workload_count": len(results),
        "status_counts": dict(sorted(status_counts.items())),
        "top_blockers": blocker_counts.most_common(),
        "top_reason_codes": reason_counts.most_common(),
        "capability_demands": dict(sorted(demand_counts.items())),
        "missing_data_counts": dict(sorted(missing_counts.items())),
        "workloads": results,
    }

