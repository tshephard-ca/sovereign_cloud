from __future__ import annotations

import zipfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any


BUNDLE_ARTIFACT_WEIGHTS = {
    "manifest.json": 10,
    "contract.yml": 20,
    "openapi.yml": 20,
    "replay_test.py": 15,
    "replay_case.yml": 10,
    "summary.json": 15,
    "privacy_report.json": 10,
}

CORE_BUNDLE_ARTIFACTS = {"contract.yml", "openapi.yml", "replay_test.py", "summary.json"}


def score_bundle_members(members: Iterable[str]) -> dict[str, Any]:
    present = sorted(set(members).intersection(BUNDLE_ARTIFACT_WEIGHTS))
    missing = [name for name in BUNDLE_ARTIFACT_WEIGHTS if name not in present]
    score = sum(BUNDLE_ARTIFACT_WEIGHTS[name] for name in present)
    blockers = [f"MISSING_CORE_ARTIFACT:{name}" for name in sorted(CORE_BUNDLE_ARTIFACTS - set(present))]
    recommendations = [
        f"ADD_RECOMMENDED_ARTIFACT:{name}"
        for name in missing
        if name not in CORE_BUNDLE_ARTIFACTS and name != "manifest.json"
    ]
    if "manifest.json" not in present:
        blockers.append("MISSING_CORE_ARTIFACT:manifest.json")

    if score >= 90 and not blockers:
        level = "complete"
    elif score >= 70 and not blockers:
        level = "review_ready_with_gaps"
    elif score >= 40:
        level = "partial"
    else:
        level = "incomplete"

    return {
        "schema_version": "1.0",
        "score": score,
        "max_score": 100,
        "level": level,
        "present": present,
        "missing": missing,
        "blockers": blockers,
        "recommendations": recommendations,
    }


def score_bundle_inputs(files: dict[str, Path | None]) -> dict[str, Any]:
    members = [name for name, path in files.items() if path is not None]
    members.append("manifest.json")
    return score_bundle_members(members)


def score_bundle_zip(path: str | Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as bundle:
        return score_bundle_members(bundle.namelist())
