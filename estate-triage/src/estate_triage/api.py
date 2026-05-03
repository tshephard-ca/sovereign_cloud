"""Public kernel API."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from collections.abc import Sequence

from estate_triage.adapters import (
    merge_evidence_sets,
    read_backup_evidence_csv,
    read_inventory_evidence_csv,
    read_utilization_evidence_csv,
)
from estate_triage.assessment import AssessmentResult, assemble_assessment
from estate_triage.config import Thresholds, load_thresholds
from estate_triage.evidence import EvidenceSet
from estate_triage.identity import IdentityOverrideSet, load_identity_overrides, resolve_identities
from estate_triage.policy import DEFAULT_POLICY_PACK, PolicyPack


def analyze_estate(
    *,
    evidence_sources: Sequence[EvidenceSet],
    thresholds: Thresholds | None = None,
    policy_pack: PolicyPack = DEFAULT_POLICY_PACK,
    identity_overrides: IdentityOverrideSet | None = None,
    now: datetime | None = None,
    warnings: list[str] | None = None,
) -> AssessmentResult:
    """Analyze canonical evidence and return a structured assessment result."""
    evidence = merge_evidence_sets(*evidence_sources)
    identity = resolve_identities(evidence, overrides=identity_overrides)
    return assemble_assessment(
        identity,
        thresholds or Thresholds(),
        policy_pack=policy_pack,
        now=now,
        warnings=warnings,
    )


def analyze_csv_estate(
    *,
    inventory_path: Path,
    backup_path: Path,
    utilization_path: Path | None = None,
    config_path: Path | None = None,
    strict: bool = False,
    now: datetime | None = None,
    policy_pack: PolicyPack = DEFAULT_POLICY_PACK,
    identity_overrides_path: Path | None = None,
) -> AssessmentResult:
    """Analyze the MVP inventory and backup CSV inputs through the kernel."""
    thresholds = load_thresholds(config_path)
    inventory = read_inventory_evidence_csv(inventory_path, strict=strict)
    backup = read_backup_evidence_csv(backup_path, strict=strict)
    evidence_sources = [inventory.evidence, backup.evidence]
    warnings = [*inventory.warnings, *backup.warnings]
    if utilization_path is not None:
        utilization = read_utilization_evidence_csv(utilization_path, strict=strict)
        evidence_sources.append(utilization.evidence)
        warnings.extend(utilization.warnings)
    return analyze_estate(
        evidence_sources=evidence_sources,
        thresholds=thresholds,
        policy_pack=policy_pack,
        identity_overrides=load_identity_overrides(identity_overrides_path),
        now=now,
        warnings=warnings,
    )
