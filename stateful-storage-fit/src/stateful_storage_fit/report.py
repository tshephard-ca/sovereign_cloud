from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .models import CandidateDataMount, FitResult, model_to_dict


MOUNT_CSV_COLUMNS = [
    "mount_path",
    "source",
    "fs_type",
    "used_gib",
    "available_gib",
    "capacity_used_pct",
    "is_candidate_data_mount",
    "data_mount_reason",
    "inferred_role",
    "device_from_iostat",
    "await_ms",
    "util_pct",
    "capacity_risk",
    "latency_risk",
    "notes",
]


def fit_result_json(result: FitResult) -> str:
    return json.dumps(model_to_dict(result), indent=2, sort_keys=False) + "\n"


def write_fit_result(result: FitResult, path: Path | None) -> None:
    data = fit_result_json(result)
    if path is None:
        print(data, end="")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def write_mount_report(candidates: Iterable[CandidateDataMount], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MOUNT_CSV_COLUMNS)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(
                {
                    "mount_path": candidate.mount_path,
                    "source": candidate.source,
                    "fs_type": candidate.fs_type,
                    "used_gib": "" if candidate.used_gib is None else candidate.used_gib,
                    "available_gib": "" if candidate.available_gib is None else candidate.available_gib,
                    "capacity_used_pct": "" if candidate.capacity_used_pct is None else candidate.capacity_used_pct,
                    "is_candidate_data_mount": str(candidate.is_candidate_data_mount).lower(),
                    "data_mount_reason": candidate.data_mount_reason,
                    "inferred_role": candidate.inferred_role,
                    "device_from_iostat": candidate.device_from_iostat or "",
                    "await_ms": "" if candidate.await_ms is None else candidate.await_ms,
                    "util_pct": "" if candidate.util_pct is None else candidate.util_pct,
                    "capacity_risk": candidate.capacity_risk,
                    "latency_risk": candidate.latency_risk,
                    "notes": ";".join(candidate.notes),
                }
            )

