"""Deterministic real-world-like bundle generator for coverage validation."""

from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from estate_triage.assessment import AssessmentResult, WorkloadAssessment
from estate_triage.models import TriageError


class GeneratedBundleSummary(BaseModel):
    bundle_path: str
    profile_name: str
    profile_source: str
    profile_description: str
    multi_source: bool = False
    input_files: list[str] = Field(default_factory=list)
    source_windows: dict[str, str] = Field(default_factory=dict)
    edge_case_files: list[str] = Field(default_factory=list)
    inventory_rows: int
    backup_rows: int
    utilization_rows: int
    scenario_counts: dict[str, int]
    backup_only_unmatched_rows: int
    expected_business_coverage: list[str]
    expected_data_quality: list[str]


class GeneratorCalibrationEvidence(BaseModel):
    """Sanitized metadata proving how a generator profile was calibrated."""

    assessment_count: int = Field(ge=1)
    inventory_rows_observed: int = Field(ge=1)
    backup_rows_observed: int = Field(ge=0)
    utilization_rows_observed: int = Field(ge=0)
    sanitization_method: str
    source_window: str | None = None
    notes: list[str] = Field(default_factory=list)


class EstateGeneratorProfile(BaseModel):
    """Deterministic estate-shape profile for synthetic evidence generation.

    A profile is not a claim that these ratios represent the market. It is the
    calibration boundary: field users can create a profile from sanitized local
    observations while the default profiles remain synthetic.
    """

    name: str
    source: str = "synthetic"
    description: str
    scenario_counts: dict[str, int]
    backup_only_unmatched_rows: int = 5
    calibration_evidence: GeneratorCalibrationEvidence | None = None
    notes: list[str] = Field(default_factory=list)


class GeneratorProfileValidation(BaseModel):
    profile_name: str
    profile_source: str
    source_declares_field_derived: bool
    calibration_evidence_present: bool
    field_derived: bool
    inventory_rows_expected: int
    backup_rows_expected: int
    utilization_rows_expected: int
    backup_only_unmatched_rows: int
    scenario_counts: dict[str, int]
    missing_scenarios: list[str]
    zero_scenarios: list[str]
    scenario_frequencies: dict[str, float]
    scenario_confidence_intervals_95: dict[str, tuple[float, float]]
    scenario_correlations: dict[str, float]
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class DerivedProfileSummary(BaseModel):
    output_path: str
    profile: EstateGeneratorProfile
    validation: GeneratorProfileValidation


SCENARIO_ORDER = [
    "migration_easy",
    "dr_large_low_change",
    "archive_powered_off_stale",
    "rightsizing_util_backed",
    "allocation_only_rightsizing",
    "snapshot_blocker",
    "no_backup_match",
    "name_only_match",
    "missing_storage_used",
    "uuid_name_conflict",
    "duplicate_name_candidates",
    "ambiguous_backup_date",
    "contradictory_records",
    "sparse_minimal",
    "rich_context",
    "extreme_outlier",
]


DEFAULT_PROFILES: dict[str, EstateGeneratorProfile] = {
    "coverage": EstateGeneratorProfile(
        name="coverage",
        source="synthetic-coverage",
        description="Broad deterministic coverage profile for regression and workflow testing.",
        scenario_counts={
            "migration_easy": 24,
            "dr_large_low_change": 12,
            "archive_powered_off_stale": 12,
            "rightsizing_util_backed": 10,
            "allocation_only_rightsizing": 8,
            "snapshot_blocker": 6,
            "no_backup_match": 5,
            "name_only_match": 5,
            "missing_storage_used": 4,
            "uuid_name_conflict": 3,
            "duplicate_name_candidates": 3,
            "ambiguous_backup_date": 2,
            "contradictory_records": 4,
            "sparse_minimal": 4,
            "rich_context": 4,
            "extreme_outlier": 3,
        },
        backup_only_unmatched_rows=5,
    ),
    "smb": EstateGeneratorProfile(
        name="smb",
        source="synthetic-profile",
        description="Smaller estate profile with fewer specialized edge cases.",
        scenario_counts={
            "migration_easy": 18,
            "dr_large_low_change": 4,
            "archive_powered_off_stale": 7,
            "rightsizing_util_backed": 4,
            "allocation_only_rightsizing": 3,
            "snapshot_blocker": 2,
            "no_backup_match": 4,
            "name_only_match": 3,
            "missing_storage_used": 2,
            "uuid_name_conflict": 1,
            "duplicate_name_candidates": 1,
            "ambiguous_backup_date": 1,
            "contradictory_records": 1,
            "sparse_minimal": 2,
            "rich_context": 1,
            "extreme_outlier": 1,
        },
        backup_only_unmatched_rows=2,
    ),
    "midmarket": EstateGeneratorProfile(
        name="midmarket",
        source="synthetic-profile",
        description="Moderate estate profile with balanced review-motion coverage.",
        scenario_counts={
            "migration_easy": 48,
            "dr_large_low_change": 20,
            "archive_powered_off_stale": 24,
            "rightsizing_util_backed": 18,
            "allocation_only_rightsizing": 14,
            "snapshot_blocker": 10,
            "no_backup_match": 10,
            "name_only_match": 8,
            "missing_storage_used": 6,
            "uuid_name_conflict": 5,
            "duplicate_name_candidates": 5,
            "ambiguous_backup_date": 4,
            "contradictory_records": 6,
            "sparse_minimal": 6,
            "rich_context": 6,
            "extreme_outlier": 5,
        },
        backup_only_unmatched_rows=8,
    ),
    "enterprise": EstateGeneratorProfile(
        name="enterprise",
        source="synthetic-profile",
        description="Larger estate profile with more identity and data-quality pressure.",
        scenario_counts={
            "migration_easy": 120,
            "dr_large_low_change": 48,
            "archive_powered_off_stale": 52,
            "rightsizing_util_backed": 42,
            "allocation_only_rightsizing": 36,
            "snapshot_blocker": 24,
            "no_backup_match": 24,
            "name_only_match": 18,
            "missing_storage_used": 16,
            "uuid_name_conflict": 12,
            "duplicate_name_candidates": 12,
            "ambiguous_backup_date": 8,
            "contradictory_records": 16,
            "sparse_minimal": 16,
            "rich_context": 16,
            "extreme_outlier": 12,
        },
        backup_only_unmatched_rows=20,
    ),
}


BACKUP_SCENARIOS = {
    "migration_easy",
    "dr_large_low_change",
    "archive_powered_off_stale",
    "rightsizing_util_backed",
    "snapshot_blocker",
    "name_only_match",
    "uuid_name_conflict",
    "duplicate_name_candidates",
    "missing_storage_used",
    "ambiguous_backup_date",
    "contradictory_records",
    "sparse_minimal",
    "rich_context",
    "extreme_outlier",
}

EXTRA_BACKUP_PER_SCENARIO = {
    "uuid_name_conflict": 1,
    "duplicate_name_candidates": 1,
}

UTILIZATION_SCENARIOS = {
    "migration_easy",
    "rightsizing_util_backed",
    "rich_context",
}

SYNTHETIC_PROFILE_SOURCES = {
    "synthetic",
    "synthetic-coverage",
    "synthetic-profile",
}


def is_field_derived_profile(profile: EstateGeneratorProfile) -> bool:
    source = profile.source.strip().lower()
    source_declares = source not in SYNTHETIC_PROFILE_SOURCES and "field" in source and "derived" in source
    return source_declares and profile.calibration_evidence is not None


def validate_generator_profile(
    profile: EstateGeneratorProfile,
    *,
    require_field_derived: bool = False,
) -> GeneratorProfileValidation:
    normalized_counts = {
        scenario: profile.scenario_counts.get(scenario, 0)
        for scenario in SCENARIO_ORDER
    }
    missing_scenarios = [
        scenario
        for scenario in SCENARIO_ORDER
        if scenario not in profile.scenario_counts
    ]
    zero_scenarios = [
        scenario
        for scenario, count in normalized_counts.items()
        if count == 0
    ]
    inventory_rows = sum(normalized_counts.values())
    backup_rows = profile.backup_only_unmatched_rows
    for scenario, count in normalized_counts.items():
        if scenario in BACKUP_SCENARIOS:
            backup_rows += count
        backup_rows += count * EXTRA_BACKUP_PER_SCENARIO.get(scenario, 0)
    utilization_rows = sum(
        count
        for scenario, count in normalized_counts.items()
        if scenario in UTILIZATION_SCENARIOS
    )
    warnings: list[str] = []
    errors: list[str] = []
    scenario_frequencies = {
        scenario: round(count / inventory_rows, 6) if inventory_rows else 0.0
        for scenario, count in normalized_counts.items()
    }
    scenario_confidence_intervals = {
        scenario: _wilson_interval(count, inventory_rows)
        for scenario, count in normalized_counts.items()
    }
    scenario_correlations = _scenario_correlations(normalized_counts, inventory_rows)
    if missing_scenarios:
        warnings.append(
            "Profile omits scenarios that will be treated as zero: "
            + ", ".join(missing_scenarios)
        )
    if zero_scenarios:
        warnings.append(
            "Profile has zero-count scenarios: "
            + ", ".join(zero_scenarios)
        )
    if inventory_rows <= 0:
        errors.append("Profile must generate at least one inventory row.")
    if profile.backup_only_unmatched_rows < 0:
        errors.append("backup_only_unmatched_rows must not be negative.")
    field_derived = is_field_derived_profile(profile)
    if require_field_derived and not field_derived:
        source = profile.source.strip().lower()
        source_declares = (
            source not in SYNTHETIC_PROFILE_SOURCES
            and "field" in source
            and "derived" in source
        )
        if not source_declares:
            errors.append(
                "Profile source must identify sanitized field-derived calibration; "
                "synthetic profiles cannot close the field-calibration gap."
            )
        if profile.calibration_evidence is None:
            errors.append(
                "Profile must include calibration_evidence when field-derived calibration is required."
            )
    if profile.calibration_evidence is not None and profile.calibration_evidence.inventory_rows_observed < inventory_rows:
        warnings.append(
            "Observed inventory rows are fewer than generated inventory rows; "
            "confirm this is an intentional scaled profile."
        )
    source = profile.source.strip().lower()
    source_declares = source not in SYNTHETIC_PROFILE_SOURCES and "field" in source and "derived" in source
    return GeneratorProfileValidation(
        profile_name=profile.name,
        profile_source=profile.source,
        source_declares_field_derived=source_declares,
        calibration_evidence_present=profile.calibration_evidence is not None,
        field_derived=field_derived,
        inventory_rows_expected=inventory_rows,
        backup_rows_expected=backup_rows,
        utilization_rows_expected=utilization_rows,
        backup_only_unmatched_rows=profile.backup_only_unmatched_rows,
        scenario_counts=normalized_counts,
        missing_scenarios=missing_scenarios,
        zero_scenarios=zero_scenarios,
        scenario_frequencies=scenario_frequencies,
        scenario_confidence_intervals_95=scenario_confidence_intervals,
        scenario_correlations=scenario_correlations,
        warnings=warnings,
        errors=errors,
    )


def _wilson_interval(count: int, total: int, *, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 0.0)
    p = count / total
    denominator = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denominator
    margin = z * ((p * (1 - p) + z**2 / (4 * total)) / total) ** 0.5 / denominator
    return (round(max(0.0, center - margin), 6), round(min(1.0, center + margin), 6))


def _scenario_correlations(counts: dict[str, int], total: int) -> dict[str, float]:
    correlations: dict[str, float] = {}
    if total <= 0:
        return correlations
    for left, right in combinations(SCENARIO_ORDER, 2):
        p_left = counts.get(left, 0) / total
        p_right = counts.get(right, 0) / total
        denominator = (p_left * (1 - p_left) * p_right * (1 - p_right)) ** 0.5
        key = f"{left}|{right}"
        if denominator == 0:
            correlations[key] = 0.0
        else:
            # Generator scenarios are single-label buckets, so p(left and right)=0.
            correlations[key] = round((0 - p_left * p_right) / denominator, 6)
    return correlations


def load_generator_profile(
    *,
    profile_name: str = "coverage",
    profile_config: Path | None = None,
) -> EstateGeneratorProfile:
    if profile_config is None:
        try:
            return DEFAULT_PROFILES[profile_name]
        except KeyError as exc:
            allowed = ", ".join(sorted(DEFAULT_PROFILES))
            raise TriageError(f"Unknown generator profile {profile_name!r}; choose one of: {allowed}.") from exc
    try:
        raw = yaml.safe_load(profile_config.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise TriageError(f"Could not read generator profile {profile_config}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise TriageError(f"Could not parse generator profile YAML {profile_config}: {exc}") from exc
    try:
        profile = EstateGeneratorProfile(**raw)
    except Exception as exc:
        raise TriageError(f"Invalid generator profile {profile_config}: {exc}") from exc
    unknown = sorted(set(profile.scenario_counts) - set(SCENARIO_ORDER))
    if unknown:
        raise TriageError(f"Generator profile contains unknown scenarios: {', '.join(unknown)}.")
    if any(count < 0 for count in profile.scenario_counts.values()):
        raise TriageError("Generator profile scenario counts must not be negative.")
    if profile.backup_only_unmatched_rows < 0:
        raise TriageError("Generator profile backup_only_unmatched_rows must not be negative.")
    return profile


def _workload_quality_codes(workload: WorkloadAssessment) -> set[str]:
    return {finding.code for finding in workload.data_quality}


def classify_workload_scenario(workload: WorkloadAssessment) -> str:
    """Map an assessed workload back to a generator scenario bucket.

    This is a calibration bridge, not a hidden recommendation model. It uses
    existing deterministic identity, reason-code, and blocking-flag outputs to
    convert a sanitized assessment into generator scenario counts.
    """
    quality_codes = _workload_quality_codes(workload)
    reason_codes = set(workload.winning_motion.reason_codes)
    blocking_flags = set(workload.blocking_flags)

    if "UUID_NAME_CONFLICT" in quality_codes or workload.identity.status == "CONFLICTED":
        return "uuid_name_conflict"
    if (
        "DUPLICATE_NAME_CANDIDATES" in quality_codes
        or (
            workload.identity.status == "DUPLICATE_CANDIDATES"
            and workload.identity.matched_by == "NAME"
        )
    ):
        return "duplicate_name_candidates"
    if workload.identity.backup is None or "NO_BACKUP_MATCH" in blocking_flags:
        return "no_backup_match"
    if "PARSE_WARNING" in quality_codes:
        return "ambiguous_backup_date"
    if {"IN_USE_EXCEEDS_PROVISIONED", "PERCENT_OUT_OF_RANGE", "NEGATIVE_VALUE"} & quality_codes:
        return "contradictory_records"
    if len(workload.missing_evidence) >= 6:
        return "sparse_minimal"
    if "MISSING_STORAGE_USED" in blocking_flags:
        return "missing_storage_used"
    if "SNAPSHOT_PRESENT" in blocking_flags:
        return "snapshot_blocker"
    if workload.winning_motion.motion == "ARCHIVE_REVIEW":
        return "archive_powered_off_stale"
    if workload.winning_motion.motion == "DR_TIER_REVIEW":
        return "dr_large_low_change"
    if workload.winning_motion.motion == "RIGHTSIZING_REVIEW":
        if {"IDLE_CPU", "OVERSIZED_MEMORY"} & reason_codes:
            return "rightsizing_util_backed"
        return "allocation_only_rightsizing"
    if workload.identity.matched_by == "NAME":
        return "name_only_match"
    return "migration_easy"


def derive_generator_profile_from_assessment(
    assessment: AssessmentResult,
    *,
    name: str,
    source: str,
    description: str,
    sanitization_method: str,
    source_window: str | None = None,
    notes: list[str] | None = None,
) -> EstateGeneratorProfile:
    counts = Counter(classify_workload_scenario(workload) for workload in assessment.workloads)
    unmatched_backup = 0
    for finding in assessment.data_quality:
        if finding.code == "UNMATCHED_BACKUP_ROWS":
            unmatched_backup += len(finding.source_refs)
    profile = EstateGeneratorProfile(
        name=name,
        source=source,
        description=description,
        scenario_counts={scenario: counts.get(scenario, 0) for scenario in SCENARIO_ORDER},
        backup_only_unmatched_rows=unmatched_backup,
        calibration_evidence=GeneratorCalibrationEvidence(
            assessment_count=1,
            inventory_rows_observed=assessment.input.get("inventory_rows", len(assessment.workloads)),
            backup_rows_observed=assessment.input.get("backup_rows", 0),
            utilization_rows_observed=assessment.input.get("utilization_rows", 0),
            sanitization_method=sanitization_method,
            source_window=source_window,
            notes=notes or [],
        ),
        notes=[
            "Derived from sanitized assessment output.",
            "Scenario buckets are deterministic approximations from assessment traces.",
            *(notes or []),
        ],
    )
    return profile


def write_generator_profile(path: Path, profile: EstateGeneratorProfile) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(profile.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )


INVENTORY_HEADERS = [
    "VM",
    "VM UUID",
    "Powerstate",
    "CPUs",
    "Memory MiB",
    "Provisioned MiB",
    "In Use MiB",
    "OS",
    "Snapshot total MiB",
    "CPU usage percent",
    "Memory usage percent",
    "Datacenter",
    "Cluster",
    "Host",
    "Tags",
    "Notes",
]

BACKUP_HEADERS = [
    "VM",
    "VM UUID",
    "backup_total_mib",
    "latest_restore_point_utc",
    "restore_point_count",
    "avg_daily_change_mib",
    "latest_incremental_mib",
    "backup_job",
    "backup_policy",
    "retention_days",
    "immutable_until_utc",
    "rpo_hours",
    "rto_tier",
    "repository",
    "protected",
    "last_success_utc",
    "last_failure_utc",
]

UTILIZATION_HEADERS = [
    "VM",
    "VM UUID",
    "sample_start_utc",
    "sample_end_utc",
    "cpu_avg_pct",
    "cpu_p95_pct",
    "cpu_max_pct",
    "memory_avg_pct",
    "memory_p95_pct",
    "memory_max_pct",
    "sample_count",
]


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})


def _write_edge_case_files(bundle: Path) -> list[str]:
    edge_dir = bundle / "edge-cases"
    edge_dir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []

    def remember(path: Path) -> None:
        files.append(str(path.relative_to(bundle)))

    duplicate_headers = edge_dir / "duplicate_headers_inventory.csv"
    duplicate_headers.write_text(
        (
            "VM,VM,VM UUID,Powerstate,CPUs,Memory MiB,In Use MiB,OS\n"
            "edge-duplicate-header,duplicate-overwrite,edge-dup-header-001,poweredOn,4,8192,40960,Generic Linux\n"
        ),
        encoding="utf-8",
    )
    remember(duplicate_headers)

    embedded_delimiters = edge_dir / "embedded_delimiters_inventory.csv"
    _write_csv(
        embedded_delimiters,
        INVENTORY_HEADERS,
        [
            _inv(
                "edge workload, quoted\nline",
                "edge-embedded-001",
                "edge_embedded_delimiters",
                used=65536,
                os="Generic Linux",
            )
        ],
    )
    remember(embedded_delimiters)

    mixed_units = edge_dir / "mixed_units_inventory.csv"
    _write_csv(
        mixed_units,
        INVENTORY_HEADERS,
        [
            _inv(
                "edge-mixed-units-001",
                "edge-mixed-units-001",
                "edge_mixed_units",
                cpus=8,
                memory="32 GiB",  # type: ignore[arg-type]
                provisioned="1.5 TiB",  # type: ignore[arg-type]
                used="512,5 GiB",
                cpu_usage="5,5%",
                memory_usage="24,5%",
            )
        ],
    )
    remember(mixed_units)

    localized_inventory = edge_dir / "localized_inventory.csv"
    _write_csv(
        localized_inventory,
        [
            "Nombre",
            "Identificador",
            "Estado",
            "CPUs asignadas",
            "Memoria MiB",
            "Usado MiB",
            "Sistema Operativo",
        ],
        [
            {
                "Nombre": "edge-localized-001",
                "Identificador": "edge-localized-001",
                "Estado": "apagado",
                "CPUs asignadas": "2",
                "Memoria MiB": "8 GiB",
                "Usado MiB": "25,5 GiB",
                "Sistema Operativo": "Unknown",
            }
        ],
    )
    remember(localized_inventory)

    irregular_lines = edge_dir / "irregular_line_endings_inventory.csv"
    irregular_lines.write_text(
        "VM,VM UUID,Powerstate,CPUs,Memory MiB,In Use MiB,OS\r\n"
        "edge-crlf-001,edge-crlf-001,poweredOn,2,4096,20480,Generic Linux\r\n",
        encoding="utf-8",
    )
    remember(irregular_lines)

    extra_columns = edge_dir / "extra_columns_inventory.csv"
    extra_columns.write_text(
        "VM,VM UUID,Powerstate,CPUs\n"
        "edge-extra-001,edge-extra-001,poweredOn,2,unexpected-extra\n",
        encoding="utf-8",
    )
    remember(extra_columns)

    missing_columns = edge_dir / "missing_columns_inventory.csv"
    missing_columns.write_text(
        "VM,VM UUID,Powerstate,CPUs,Memory MiB\n"
        "edge-missing-001,edge-missing-001,poweredOn\n",
        encoding="utf-8",
    )
    remember(missing_columns)

    malformed = edge_dir / "malformed_inventory.csv"
    malformed.write_text(
        'VM,VM UUID,Powerstate\n"edge-malformed,edge-malformed-001,poweredOn\n',
        encoding="utf-8",
    )
    remember(malformed)

    non_utf8 = edge_dir / "non_utf8_inventory.csv"
    non_utf8.write_bytes(b"VM,VM UUID\ncaf\xe9,edge-nonutf8-001\n")
    remember(non_utf8)

    localized_backup = edge_dir / "localized_backup_export.csv"
    _write_csv(
        localized_backup,
        [
            "Nombre",
            "Identificador",
            "Total Respaldo MiB",
            "latest_restore_point_utc",
            "restore_point_count",
            "avg_daily_change_mib",
        ],
        [
            {
                "Nombre": "edge-localized-001",
                "Identificador": "edge-localized-001",
                "Total Respaldo MiB": "1,5 TiB",
                "latest_restore_point_utc": "31.03.2026",
                "restore_point_count": "12",
                "avg_daily_change_mib": "512,5",
            }
        ],
    )
    remember(localized_backup)

    manifest = edge_dir / "edge-case-manifest.yml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "purpose": "Generated messy CSV fixtures for local adapter and readiness validation.",
                "files": files,
                "expected_signals": [
                    "duplicate headers",
                    "embedded delimiters and newlines",
                    "mixed MiB/GiB/TiB and decimal-comma units",
                    "localized headers and localized power-state text",
                    "irregular line endings",
                    "extra and missing CSV columns",
                    "malformed quoting",
                    "non-UTF-8 input rejection",
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    remember(manifest)
    return files


def _inv(
    name: str,
    uuid: str,
    scenario: str,
    *,
    power: str = "poweredOn",
    cpus: int = 4,
    memory: int = 8192,
    provisioned: int = 153600,
    used: int | str = 76800,
    os: str = "Generic Linux",
    snapshot: int = 0,
    cpu_usage: int | str = "",
    memory_usage: int | str = "",
    dc: str = "region-a",
    cluster: str = "cluster-a",
    host: str = "host-a",
) -> dict[str, Any]:
    return {
        "VM": name,
        "VM UUID": uuid,
        "Powerstate": power,
        "CPUs": cpus,
        "Memory MiB": memory,
        "Provisioned MiB": provisioned,
        "In Use MiB": used,
        "OS": os,
        "Snapshot total MiB": snapshot,
        "CPU usage percent": cpu_usage,
        "Memory usage percent": memory_usage,
        "Datacenter": dc,
        "Cluster": cluster,
        "Host": host,
        "Tags": f"scenario:{scenario}",
        "Notes": f"scenario={scenario}; synthetic generated coverage case",
    }


def _bak(
    name: str,
    uuid: str,
    scenario: str,
    *,
    total: int = 100000,
    restore: str = "2026-04-25T02:00:00Z",
    points: int = 14,
    change: int = 512,
    incremental: int = 700,
    policy: str = "policy-standard",
    repository: str = "repo-a",
) -> dict[str, Any]:
    return {
        "VM": name,
        "VM UUID": uuid,
        "backup_total_mib": total,
        "latest_restore_point_utc": restore,
        "restore_point_count": points,
        "avg_daily_change_mib": change,
        "latest_incremental_mib": incremental,
        "backup_job": f"job-{scenario}",
        "backup_policy": policy,
        "retention_days": 30 if policy == "policy-standard" else 90,
        "immutable_until_utc": "2026-05-25T02:00:00Z",
        "rpo_hours": 24,
        "rto_tier": "standard",
        "repository": repository,
        "protected": "true",
        "last_success_utc": restore if restore and "/" not in restore else "",
        "last_failure_utc": "",
    }


def _util(
    name: str,
    uuid: str,
    *,
    cpu_avg: int,
    cpu_p95: int,
    cpu_max: int,
    mem_avg: int,
    mem_p95: int,
    mem_max: int,
    samples: int = 336,
) -> dict[str, Any]:
    return {
        "VM": name,
        "VM UUID": uuid,
        "sample_start_utc": "2026-04-01T00:00:00Z",
        "sample_end_utc": "2026-04-15T00:00:00Z",
        "cpu_avg_pct": cpu_avg,
        "cpu_p95_pct": cpu_p95,
        "cpu_max_pct": cpu_max,
        "memory_avg_pct": mem_avg,
        "memory_p95_pct": mem_p95,
        "memory_max_pct": mem_max,
        "sample_count": samples,
    }


def _mapping_files(bundle: Path) -> None:
    mappings = {
        "inventory-map.yml": {
            "source_kind": "inventory",
            "schema_version": "1.0.0",
            "columns": {
                "name": "VM",
                "uuid": "VM UUID",
                "power_state": "Powerstate",
                "cpu_count": "CPUs",
                "memory_mib": "Memory MiB",
                "provisioned_mib": "Provisioned MiB",
                "in_use_mib": "In Use MiB",
                "os": "OS",
                "snapshot_total_mib": "Snapshot total MiB",
                "cpu_usage_pct": "CPU usage percent",
                "memory_usage_pct": "Memory usage percent",
                "datacenter": "Datacenter",
                "cluster": "Cluster",
                "host": "Host",
                "tags": "Tags",
                "notes": "Notes",
            },
        },
        "backup-map.yml": {
            "source_kind": "backup",
            "schema_version": "1.0.0",
            "columns": {
                "name": "VM",
                "uuid": "VM UUID",
                "backup_total_mib": "backup_total_mib",
                "latest_restore_point_utc": "latest_restore_point_utc",
                "restore_point_count": "restore_point_count",
                "avg_daily_change_mib": "avg_daily_change_mib",
                "latest_incremental_mib": "latest_incremental_mib",
                "backup_job": "backup_job",
                "backup_policy": "backup_policy",
                "retention_days": "retention_days",
                "immutable_until_utc": "immutable_until_utc",
                "rpo_hours": "rpo_hours",
                "rto_tier": "rto_tier",
                "repository": "repository",
                "protected": "protected",
                "last_success_utc": "last_success_utc",
                "last_failure_utc": "last_failure_utc",
            },
        },
        "utilization-map.yml": {
            "source_kind": "utilization",
            "schema_version": "1.0.0",
            "columns": {
                "name": "VM",
                "uuid": "VM UUID",
                "sample_start_utc": "sample_start_utc",
                "sample_end_utc": "sample_end_utc",
                "cpu_avg_pct": "cpu_avg_pct",
                "cpu_p95_pct": "cpu_p95_pct",
                "cpu_max_pct": "cpu_max_pct",
                "memory_avg_pct": "memory_avg_pct",
                "memory_p95_pct": "memory_p95_pct",
                "memory_max_pct": "memory_max_pct",
                "sample_count": "sample_count",
            },
        },
    }
    for filename, payload in mappings.items():
        path = bundle / "mappings" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _manifest(bundle: Path, *, multi_source: bool = False) -> None:
    inputs = [
        {"path": "inputs/inventory.csv", "kind": "inventory", "mapping": "mappings/inventory-map.yml"},
        {"path": "inputs/backup_export.csv", "kind": "backup", "mapping": "mappings/backup-map.yml"},
        {"path": "inputs/utilization.csv", "kind": "utilization", "mapping": "mappings/utilization-map.yml"},
    ]
    if multi_source:
        inputs.insert(
            1,
            {
                "path": "inputs/inventory_secondary.csv",
                "kind": "inventory",
                "mapping": "mappings/inventory-map.yml",
            },
        )
        inputs.insert(
            3,
            {
                "path": "inputs/backup_secondary.csv",
                "kind": "backup",
                "mapping": "mappings/backup-map.yml",
            },
        )
    manifest = {
        "bundle_version": "1.0.0",
        "assessment_id": "generated-real-world-coverage",
        "inputs": inputs,
        "policy": {"thresholds": "policies/thresholds.yml"},
        "privacy": {"redaction_mode": "strict", "hash_salt_file": ".local-salt"},
        "outputs": {"directory": "outputs"},
        "feedback": "feedback/feedback.yml",
    }
    (bundle / "manifest.yml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    thresholds = {
        "top_n": 25,
        "recent_backup_days": 14,
        "stale_backup_days": 60,
        "high_cpu_count": 8,
        "high_memory_mib": 32768,
        "small_workload_mib": 204800,
        "large_backup_mib": 1048576,
        "low_change_rate_pct": 1.0,
        "high_backup_to_used_ratio": 3.0,
        "many_restore_points": 30,
        "idle_cpu_pct": 5,
        "low_memory_usage_pct": 30,
    }
    policy_dir = bundle / "policies"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "thresholds.yml").write_text(yaml.safe_dump(thresholds, sort_keys=False), encoding="utf-8")
    feedback_dir = bundle / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    feedback = {
        "assessment_id": "generated-real-world-coverage",
        "feedback": [
            {
                "workload_key": "replace-after-run",
                "finding": "DR_TIER_REVIEW",
                "outcome": "useful",
                "notes": "synthetic feedback placeholder for local workflow validation",
            }
        ],
    }
    (feedback_dir / "feedback.yml").write_text(yaml.safe_dump(feedback, sort_keys=False), encoding="utf-8")


def generate_real_world_bundle(
    output: Path,
    *,
    overwrite: bool = False,
    profile_name: str = "coverage",
    profile_config: Path | None = None,
    multi_source: bool = False,
    edge_cases: bool = False,
) -> GeneratedBundleSummary:
    """Generate a deterministic, broad-coverage synthetic estate bundle."""
    profile = load_generator_profile(profile_name=profile_name, profile_config=profile_config)
    profile_validation = validate_generator_profile(profile)
    if profile_validation.errors:
        raise TriageError("; ".join(profile_validation.errors))
    if output.exists() and any(output.iterdir()):
        if not overwrite:
            raise TriageError(f"Output directory {output} is not empty; pass --overwrite.")
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)

    inventory: list[dict[str, Any]] = []
    backups: list[dict[str, Any]] = []
    utilization: list[dict[str, Any]] = []
    scenarios: Counter[str] = Counter()

    def add(inv: dict[str, Any], backup: dict[str, Any] | None = None, util: dict[str, Any] | None = None) -> None:
        inventory.append(inv)
        scenario = str(inv["Tags"]).split("scenario:", 1)[1]
        scenarios[scenario] += 1
        if backup is not None:
            backups.append(backup)
        if util is not None:
            utilization.append(util)

    def count(scenario: str) -> int:
        return profile.scenario_counts.get(scenario, 0)

    for i in range(1, count("migration_easy") + 1):
        name = f"mig-app-{i:03d}"
        uuid = f"gen-mig-{i:03d}"
        used = 45000 + i * 1800
        add(
            _inv(name, uuid, "migration_easy", cpus=2 + i % 3, memory=4096 + (i % 2) * 4096, used=used),
            _bak(name, uuid, "migration_easy", total=int(used * 1.5), change=max(128, int(used * 0.004))),
            _util(name, uuid, cpu_avg=12, cpu_p95=35, cpu_max=70, mem_avg=45, mem_p95=65, mem_max=85),
        )

    for i in range(1, count("dr_large_low_change") + 1):
        name = f"dr-data-{i:03d}"
        uuid = f"gen-dr-{i:03d}"
        used = 550000 + i * 65000
        add(
            _inv(name, uuid, "dr_large_low_change", cpus=4 + i % 6, memory=16384 + (i % 3) * 8192, provisioned=used * 2, used=used),
            _bak(
                name,
                uuid,
                "dr_large_low_change",
                total=max(1048576, used * 4),
                points=45 + i,
                change=max(512, int(used * 0.002)),
                policy="policy-extended",
                repository="repo-b",
            ),
        )

    for i in range(1, count("archive_powered_off_stale") + 1):
        name = f"archive-off-{i:03d}"
        uuid = f"gen-archive-{i:03d}"
        used = 18000 + i * 2500
        add(
            _inv(name, uuid, "archive_powered_off_stale", power="poweredOff", cpus=2, memory=4096, used=used, os="Unknown"),
            _bak(
                name,
                uuid,
                "archive_powered_off_stale",
                total=used + 10000,
                restore="2025-11-15T02:00:00Z",
                points=3,
                change=128,
                policy="policy-archive",
                repository="repo-c",
            ),
        )

    for i in range(1, count("rightsizing_util_backed") + 1):
        name = f"rightsize-util-{i:03d}"
        uuid = f"gen-rsu-{i:03d}"
        used = 360000 + i * 25000
        add(
            _inv(name, uuid, "rightsizing_util_backed", cpus=12 + i % 4, memory=65536, provisioned=used * 2, used=used, cpu_usage="", memory_usage=""),
            _bak(name, uuid, "rightsizing_util_backed", total=int(used * 1.2), restore="2025-12-01T02:00:00Z", points=12, change=int(used * 0.04)),
            _util(name, uuid, cpu_avg=2, cpu_p95=4, cpu_max=12, mem_avg=18, mem_p95=25, mem_max=45),
        )

    for i in range(1, count("allocation_only_rightsizing") + 1):
        name = f"alloc-review-{i:03d}"
        uuid = f"gen-alloc-{i:03d}"
        add(
            _inv(name, uuid, "allocation_only_rightsizing", power="", cpus=16, memory=65536, provisioned=900000, used=420000, cpu_usage="", memory_usage=""),
            None,
            None,
        )

    for i in range(1, count("snapshot_blocker") + 1):
        name = f"snapshot-app-{i:03d}"
        uuid = f"gen-snap-{i:03d}"
        add(
            _inv(name, uuid, "snapshot_blocker", used=70000, snapshot=4096 * i),
            _bak(name, uuid, "snapshot_blocker", total=100000, change=256),
        )

    for i in range(1, count("no_backup_match") + 1):
        name = f"unprotected-app-{i:03d}"
        uuid = f"gen-nobak-{i:03d}"
        add(_inv(name, uuid, "no_backup_match", used=125000 + i * 10000), None)

    for i in range(1, count("name_only_match") + 1):
        name = f"name-only-{i:03d}"
        add(
            _inv(name, "", "name_only_match", cpus=2, memory=4096, used=60000),
            _bak(name, "", "name_only_match", total=85000, change=300),
        )

    for i in range(1, count("uuid_name_conflict") + 1):
        name = f"conflict-app-{i:03d}"
        uuid = f"gen-conflict-{i:03d}"
        add(
            _inv(name, uuid, "uuid_name_conflict", used=90000),
            _bak(f"renamed-conflict-{i:03d}", uuid, "uuid_name_conflict", total=130000, change=500),
        )
        backups.append(_bak(name, f"other-conflict-{i:03d}", "uuid_name_conflict", total=130000, change=500))

    for i in range(1, count("duplicate_name_candidates") + 1):
        name = f"duplicate-name-{i:03d}"
        add(
            _inv(name, "", "duplicate_name_candidates", used=85000),
            _bak(name, "", "duplicate_name_candidates", total=100000, change=400),
        )
        backups.append(_bak(name, "", "duplicate_name_candidates", total=120000, change=450))

    for i in range(1, count("missing_storage_used") + 1):
        name = f"missing-used-{i:03d}"
        uuid = f"gen-missing-used-{i:03d}"
        add(
            _inv(name, uuid, "missing_storage_used", used="" if i % 2 else 0),
            _bak(name, uuid, "missing_storage_used", total=100000, change=400),
        )

    for i in range(1, count("ambiguous_backup_date") + 1):
        name = f"ambiguous-date-{i:03d}"
        uuid = f"gen-ambiguous-date-{i:03d}"
        add(
            _inv(name, uuid, "ambiguous_backup_date", used=90000),
            _bak(name, uuid, "ambiguous_backup_date", total=130000, restore="04/05/2026", change=500),
        )

    for i in range(1, count("contradictory_records") + 1):
        name = f"contradictory-{i:03d}"
        uuid = f"gen-contradictory-{i:03d}"
        add(
            _inv(
                name,
                uuid,
                "contradictory_records",
                cpus=4,
                memory=16384,
                provisioned=100000,
                used=180000 + i * 1000,
                cpu_usage="135%",
                memory_usage="110%",
            ),
            _bak(name, uuid, "contradictory_records", total=240000, change=400),
        )

    for i in range(1, count("sparse_minimal") + 1):
        name = f"sparse-minimal-{i:03d}"
        uuid = f"gen-sparse-{i:03d}"
        add(
            _inv(
                name,
                uuid,
                "sparse_minimal",
                power="",
                cpus="",  # type: ignore[arg-type]
                memory="",  # type: ignore[arg-type]
                provisioned="",  # type: ignore[arg-type]
                used="",
                os="",
            ),
            _bak(
                name,
                uuid,
                "sparse_minimal",
                total=75000,
                restore="",
                points="",  # type: ignore[arg-type]
                change="",  # type: ignore[arg-type]
            ),
        )

    for i in range(1, count("rich_context") + 1):
        name = f"rich-context-{i:03d}"
        uuid = f"gen-rich-{i:03d}"
        used = 240000 + i * 12000
        add(
            _inv(
                name,
                uuid,
                "rich_context",
                cpus=6,
                memory=24576,
                provisioned=used * 2,
                used=used,
                os="Generic Linux",
                dc="region-c",
                cluster="cluster-prod",
                host="host-prod",
            ),
            _bak(
                name,
                uuid,
                "rich_context",
                total=int(used * 1.4),
                points=32,
                change=int(used * 0.012),
                policy="policy-extended",
                repository="repo-context",
            ),
            _util(name, uuid, cpu_avg=18, cpu_p95=42, cpu_max=80, mem_avg=52, mem_p95=73, mem_max=91),
        )

    for i in range(1, count("extreme_outlier") + 1):
        name = f"extreme-outlier-{i:03d}"
        uuid = f"gen-extreme-{i:03d}"
        add(
            _inv(
                name,
                uuid,
                "extreme_outlier",
                cpus=128,
                memory=1048576,
                provisioned=2097152,
                used=1572864,
                os="Generic Linux",
                snapshot=262144,
            ),
            _bak(
                name,
                uuid,
                "extreme_outlier",
                total=8388608,
                points=365,
                change=1024,
                policy="policy-extended",
                repository="repo-outlier",
            ),
        )

    for i in range(1, profile.backup_only_unmatched_rows + 1):
        backups.append(
            _bak(
                f"backup-only-{i:03d}",
                f"gen-backup-only-{i:03d}",
                "backup_only_unmatched",
                total=50000,
                change=100,
            )
        )

    input_files = ["inputs/inventory.csv", "inputs/backup_export.csv", "inputs/utilization.csv"]
    source_windows = {
        "inputs/inventory.csv": "2026-04-28T00:00:00Z",
        "inputs/backup_export.csv": "2026-04-30T00:00:00Z",
        "inputs/utilization.csv": "2026-04-01T00:00:00Z/2026-04-15T00:00:00Z",
    }
    if multi_source:
        inventory_split = max(1, int(len(inventory) * 0.75))
        backup_split = max(1, int(len(backups) * 0.75))
        _write_csv(output / "inputs" / "inventory.csv", INVENTORY_HEADERS, inventory[:inventory_split])
        _write_csv(output / "inputs" / "inventory_secondary.csv", INVENTORY_HEADERS, inventory[inventory_split:])
        _write_csv(output / "inputs" / "backup_export.csv", BACKUP_HEADERS, backups[:backup_split])
        _write_csv(output / "inputs" / "backup_secondary.csv", BACKUP_HEADERS, backups[backup_split:])
        input_files = [
            "inputs/inventory.csv",
            "inputs/inventory_secondary.csv",
            "inputs/backup_export.csv",
            "inputs/backup_secondary.csv",
            "inputs/utilization.csv",
        ]
        source_windows.update(
            {
                "inputs/inventory_secondary.csv": "2026-03-15T00:00:00Z",
                "inputs/backup_secondary.csv": "2026-04-20T00:00:00Z",
            }
        )
    else:
        _write_csv(output / "inputs" / "inventory.csv", INVENTORY_HEADERS, inventory)
        _write_csv(output / "inputs" / "backup_export.csv", BACKUP_HEADERS, backups)
    _write_csv(output / "inputs" / "utilization.csv", UTILIZATION_HEADERS, utilization)
    edge_case_files = _write_edge_case_files(output) if edge_cases else []
    _mapping_files(output)
    _manifest(output, multi_source=multi_source)
    (output / "source-metadata.yml").write_text(
        yaml.safe_dump(
            {
                "multi_source": multi_source,
                "source_windows": source_windows,
                "notes": [
                    "Secondary inventory intentionally models stale export timing.",
                    "Secondary backup intentionally models a different capture window.",
                    "Split sources model partial source coverage without duplicating rows.",
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (output / "generator-profile.yml").write_text(
        yaml.safe_dump(profile.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )

    coverage = GeneratedBundleSummary(
        bundle_path=str(output),
        profile_name=profile.name,
        profile_source=profile.source,
        profile_description=profile.description,
        multi_source=multi_source,
        input_files=input_files,
        source_windows=source_windows,
        edge_case_files=edge_case_files,
        inventory_rows=len(inventory),
        backup_rows=len(backups),
        utilization_rows=len(utilization),
        scenario_counts={scenario: scenarios.get(scenario, 0) for scenario in SCENARIO_ORDER},
        backup_only_unmatched_rows=profile.backup_only_unmatched_rows,
        expected_business_coverage=[
            "migration review candidates",
            "archive review candidates",
            "allocation-only right-sizing candidates",
            "utilization-backed right-sizing candidates",
            "DR tier review candidates",
            "missing-data requests",
            "privacy-safe redacted handoff output",
            "sparse minimal input readiness",
            "rich context input preservation",
            "extreme outlier triage pressure",
        ],
        expected_data_quality=[
            "UUID/name conflict",
            "duplicate name candidates",
            "unmatched inventory rows",
            "unmatched backup rows",
            "missing storage used",
            "ambiguous date parsing",
            "snapshot blocking flags",
            "contradictory storage and percent ranges",
            "sparse source rows",
            "extreme outlier values",
            "duplicate headers",
            "malformed CSV rejection",
            "embedded delimiters and newlines",
            "mixed storage units",
            "localized headers and power-state values",
            "non-UTF-8 rejection",
        ],
    )
    (output / "coverage.json").write_text(
        json.dumps(coverage.model_dump(), indent=2) + "\n",
        encoding="utf-8",
    )
    return coverage
