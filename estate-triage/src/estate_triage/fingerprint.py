"""Input fingerprint helpers for reproducible local bundles."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from pydantic import BaseModel


class InputFingerprint(BaseModel):
    path: str
    sha256: str
    row_count: int
    columns_hash: str
    columns: list[str]


def fingerprint_csv(path: Path) -> InputFingerprint:
    data = path.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        row_count = sum(1 for _ in reader)
    columns_hash = hashlib.sha256("|".join(columns).encode("utf-8")).hexdigest()
    return InputFingerprint(
        path=str(path),
        sha256=sha256,
        row_count=row_count,
        columns_hash=columns_hash,
        columns=columns,
    )


def write_fingerprints(path: Path, fingerprints: list[InputFingerprint]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"inputs": [fp.model_dump() for fp in fingerprints]}, indent=2) + "\n",
        encoding="utf-8",
    )
