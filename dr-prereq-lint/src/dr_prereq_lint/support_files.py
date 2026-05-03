"""Optional support-file loaders for generated operational context."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Iterable

import yaml

from .models import AcceptedRisk, Finding, ObservedPrerequisite, OwnerMapEntry, RecoverySetMetadata
from .normalize import normalize_fqdn, normalize_ip, split_multi


def load_owner_map(path: str | Path | None) -> list[OwnerMapEntry]:
    if path is None:
        return []
    entries: list[OwnerMapEntry] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            owner_team = str(row.get("owner_team") or "").strip()
            if not owner_team:
                continue
            entries.append(
                OwnerMapEntry(
                    owner_team=owner_team,
                    categories=[item.strip() for item in split_multi(row.get("category")) if item.strip()],
                    contact=str(row.get("contact") or "").strip(),
                    notes=str(row.get("notes") or "").strip(),
                )
            )
    return entries


def owner_label_for_category(owner_map: list[OwnerMapEntry], category: str) -> str:
    for entry in owner_map:
        if category in entry.categories:
            if entry.contact:
                return f"{entry.owner_team} ({entry.contact})"
            return entry.owner_team
    return ""


def owner_contact_by_category(owner_map: list[OwnerMapEntry]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for entry in owner_map:
        for category in entry.categories:
            result[category] = {
                "owner_team": entry.owner_team,
                "contact": entry.contact,
                "notes": entry.notes,
            }
    return result


def load_accepted_risks(path: str | Path | None) -> list[AcceptedRisk]:
    if path is None:
        return []
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    risks = payload.get("accepted_risks", []) if isinstance(payload, dict) else []
    result: list[AcceptedRisk] = []
    for idx, item in enumerate(risks, start=1):
        if not isinstance(item, dict):
            continue
        result.append(
            AcceptedRisk(
                id=str(item.get("id") or f"accepted_risk_{idx}"),
                category=str(item.get("category") or "").strip(),
                name=str(item.get("name") or "").strip(),
                reason=str(item.get("reason") or "").strip(),
                expires=str(item.get("expires") or "").strip(),
                source_row=idx,
            )
        )
    return result


def matching_accepted_risk(item: Finding | ObservedPrerequisite, risks: list[AcceptedRisk]) -> AcceptedRisk | None:
    if not risks:
        return None
    names = _candidate_names(item)
    for risk in risks:
        if risk.category and risk.category != item.category:
            continue
        if risk.expires and _is_expired(risk.expires):
            continue
        risk_name = _normalize_candidate(risk.name)
        if risk_name and risk_name in names:
            return risk
    return None


def load_recovery_set_metadata(path: str | Path | None) -> dict[str, RecoverySetMetadata]:
    if path is None:
        return {}
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    items = payload.get("recovery_sets", []) if isinstance(payload, dict) else []
    result: dict[str, RecoverySetMetadata] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        result[name] = RecoverySetMetadata(
            name=name,
            purpose=str(item.get("purpose") or "").strip(),
            site=str(item.get("site") or "").strip(),
            notes=str(item.get("notes") or "").strip(),
        )
    return result


def recovery_set_names_from_metadata(path: str | Path | None) -> list[str]:
    return sorted(load_recovery_set_metadata(path).keys())


def _candidate_names(item: Finding | ObservedPrerequisite) -> set[str]:
    values: list[str] = [
        getattr(item, "prerequisite_name", ""),
        getattr(item, "prerequisite_target", ""),
        getattr(item, "prerequisite_target_ip", ""),
    ]
    values.extend(getattr(item, "example_qnames", []))
    values.extend(getattr(item, "example_answer_names", []))
    values.extend(getattr(item, "example_answer_ips", []))
    return {_normalize_candidate(value) for value in values if _normalize_candidate(value)}


def _normalize_candidate(value: str) -> str:
    normalized_ip = normalize_ip(value)
    if normalized_ip:
        return normalized_ip
    normalized_name = normalize_fqdn(value)
    return normalized_name or str(value or "").strip().lower()


def _is_expired(value: str) -> bool:
    try:
        return date.fromisoformat(value) < date.today()
    except ValueError:
        return False
