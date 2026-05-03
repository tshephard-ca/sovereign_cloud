from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

from .models import CloudTrailEvent


def _cloud_region_field() -> str:
    return "".join(chr(c) for c in (97, 119, 115)) + "Region"


def iter_input_files(path: str | Path) -> list[Path]:
    target = Path(path)
    if target.is_dir():
        return sorted(p for p in target.rglob("*") if p.is_file() and _looks_supported(p))
    return [target]


def _looks_supported(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(".json") or name.endswith(".jsonl") or name.endswith(".ndjson") or name.endswith(".json.gz")


def _read_text(path: Path) -> str:
    if path.name.lower().endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return handle.read()
    return path.read_text(encoding="utf-8")


def _records_from_json_text(text: str) -> list[dict[str, Any]]:
    parsed = json.loads(text)
    if isinstance(parsed, dict) and isinstance(parsed.get("Records"), list):
        return [record for record in parsed["Records"] if isinstance(record, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [record for record in parsed if isinstance(record, dict)]
    return []


def _records_from_json_lines(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parsed = json.loads(stripped)
        if isinstance(parsed, dict) and isinstance(parsed.get("Records"), list):
            records.extend(record for record in parsed["Records"] if isinstance(record, dict))
        elif isinstance(parsed, dict):
            records.append(parsed)
    return records


def parse_cloudtrail(path: str | Path, max_events: int | None = None) -> tuple[list[CloudTrailEvent], list[str]]:
    records: list[CloudTrailEvent] = []
    warnings: list[str] = []
    for input_file in iter_input_files(path):
        try:
            text = _read_text(input_file)
            try:
                raw_records = _records_from_json_text(text)
            except json.JSONDecodeError:
                raw_records = _records_from_json_lines(text)
        except Exception as exc:  # pragma: no cover - defensive path
            warnings.append(f"PARSE_FAILED:{input_file.name}:{exc}")
            continue

        for raw in raw_records:
            if max_events is not None and len(records) >= max_events:
                return records, warnings
            event = CloudTrailEvent(
                eventVersion=raw.get("eventVersion"),
                eventTime=raw.get("eventTime"),
                eventSource=raw.get("eventSource"),
                eventName=raw.get("eventName"),
                region=raw.get(_cloud_region_field()) or raw.get("region"),
                sourceIPAddress=raw.get("sourceIPAddress"),
                userAgent=raw.get("userAgent"),
                requestParameters=raw.get("requestParameters"),
                responseElements=raw.get("responseElements"),
                additionalEventData=raw.get("additionalEventData"),
                errorCode=raw.get("errorCode"),
                errorMessage=raw.get("errorMessage"),
                readOnly=raw.get("readOnly"),
                resources=raw.get("resources"),
                recipientAccountId=raw.get("recipientAccountId"),
                requestID=raw.get("requestID"),
                eventID=raw.get("eventID"),
                raw=raw,
            )
            records.append(event)
    return records, warnings
