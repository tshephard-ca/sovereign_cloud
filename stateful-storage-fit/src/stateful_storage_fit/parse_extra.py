from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_text(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def _flatten_findmnt(filesystems: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    for item in filesystems:
        rows.append(
            {
                "target": item.get("target"),
                "source": item.get("source"),
                "fstype": item.get("fstype"),
                "options": item.get("options"),
            }
        )
        children = item.get("children")
        if isinstance(children, list):
            _flatten_findmnt(children, rows)


def parse_findmnt_json_text(text: str) -> dict[str, Any]:
    data = json.loads(text)
    rows: list[dict[str, Any]] = []
    filesystems = data.get("filesystems") if isinstance(data, dict) else None
    if isinstance(filesystems, list):
        _flatten_findmnt(filesystems, rows)
    return {"mount_count": len(rows), "mounts": rows[:200]}


def _flatten_lsblk(devices: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    for item in devices:
        rows.append(
            {
                "name": item.get("name"),
                "type": item.get("type"),
                "pkname": item.get("pkname"),
                "mountpoint": item.get("mountpoint"),
                "fstype": item.get("fstype"),
                "size": item.get("size"),
            }
        )
        children = item.get("children")
        if isinstance(children, list):
            _flatten_lsblk(children, rows)


def parse_lsblk_json_text(text: str) -> dict[str, Any]:
    data = json.loads(text)
    rows: list[dict[str, Any]] = []
    devices = data.get("blockdevices") if isinstance(data, dict) else None
    if isinstance(devices, list):
        _flatten_lsblk(devices, rows)
    return {"device_count": len(rows), "devices": rows[:200]}


def parse_key_value_lines(text: str) -> dict[str, Any]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return {"line_count": len(lines), "sample": lines[:50]}


def load_extra_evidence(
    *,
    findmnt_json: Path | None = None,
    lsblk_json: Path | None = None,
    blkid: Path | None = None,
    pvs: Path | None = None,
    vgs: Path | None = None,
    lvs: Path | None = None,
    inode_df: Path | None = None,
    du_summary: Path | None = None,
) -> tuple[dict[str, Any], list[str]]:
    extra: dict[str, Any] = {}
    warnings: list[str] = []
    for name, path, parser in [
        ("findmnt_json", findmnt_json, parse_findmnt_json_text),
        ("lsblk_json", lsblk_json, parse_lsblk_json_text),
        ("blkid", blkid, parse_key_value_lines),
        ("pvs", pvs, parse_key_value_lines),
        ("vgs", vgs, parse_key_value_lines),
        ("lvs", lvs, parse_key_value_lines),
        ("inode_df", inode_df, parse_key_value_lines),
        ("du_summary", du_summary, parse_key_value_lines),
    ]:
        text = _load_text(path)
        if text is None:
            continue
        try:
            extra[name] = parser(text)
        except (ValueError, json.JSONDecodeError) as exc:
            warnings.append(f"EXTRA_EVIDENCE_PARSE_FAILED:{name}:{exc}")
    return extra, warnings

