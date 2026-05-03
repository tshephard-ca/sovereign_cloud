from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from pathlib import Path

import yaml

from .bundle import read_bundle_artifacts, validate_case_bundle, zip_directory
from .models import CaseBundleManifest, CorpusSummary


def import_bundle(bundle_path: str | Path, corpus_dir: str | Path, *, strict_redaction: bool = True) -> Path:
    ok, errors, _ = validate_case_bundle(bundle_path, strict_redaction=strict_redaction)
    if not ok:
        raise ValueError("; ".join(errors))
    artifacts = read_bundle_artifacts(bundle_path)
    manifest = CaseBundleManifest(**yaml.safe_load(artifacts["case.yml"]))
    root = Path(corpus_dir)
    bundle_root = root / "bundles"
    index_root = root / "index"
    bundle_root.mkdir(parents=True, exist_ok=True)
    index_root.mkdir(parents=True, exist_ok=True)
    output = bundle_root / f"{manifest.case_id}.zip"
    if Path(bundle_path).is_dir():
        zip_directory(bundle_path, output)
    else:
        shutil.copyfile(bundle_path, output)
    (index_root / f"{manifest.case_id}.json").write_text(json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def summarize_corpus(corpus_dir: str | Path) -> CorpusSummary:
    root = Path(corpus_dir)
    workload_types: Counter[str] = Counter()
    observed_families: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    mismatch_codes: Counter[str] = Counter()
    blocker_codes: Counter[str] = Counter()
    review_codes: Counter[str] = Counter()
    warnings: set[str] = set()
    case_count = 0
    for bundle_path in sorted((root / "bundles").glob("*.zip")):
        artifacts = read_bundle_artifacts(bundle_path)
        manifest = CaseBundleManifest(**yaml.safe_load(artifacts["case.yml"]))
        case_count += 1
        workload_types[manifest.workload_type] += 1
        for family in manifest.observed_families:
            observed_families[family] += 1
        if "compat-summary.json" in artifacts:
            summary = json.loads(artifacts["compat-summary.json"])
            status_counts[summary.get("compatibility_status", "UNKNOWN")] += 1
            for warning in summary.get("warnings", []):
                warnings.add(str(warning))
        for name, text in artifacts.items():
            if not name.startswith("mismatches/") or not name.endswith(".csv"):
                continue
            for row in csv.DictReader(text.splitlines()):
                code = row.get("mismatch_code") or "UNKNOWN"
                severity = row.get("severity") or "INFO"
                mismatch_codes[code] += 1
                if severity == "BLOCKER":
                    blocker_codes[code] += 1
                elif severity == "REVIEW":
                    review_codes[code] += 1
    return CorpusSummary(
        case_count=case_count,
        workload_types=dict(sorted(workload_types.items())),
        observed_families=dict(sorted(observed_families.items())),
        status_counts=dict(sorted(status_counts.items())),
        mismatch_code_counts=dict(sorted(mismatch_codes.items())),
        blocker_code_counts=dict(sorted(blocker_codes.items())),
        review_code_counts=dict(sorted(review_codes.items())),
        warnings=sorted(warnings),
    )


def corpus_summary_markdown(summary: CorpusSummary) -> str:
    lines = ["# Compatibility Corpus Summary", "", f"Cases: {summary.case_count}", ""]
    lines.extend(_section("Workload Types", summary.workload_types))
    lines.extend(_section("Observed Families", summary.observed_families))
    lines.extend(_section("Compatibility Status", summary.status_counts))
    lines.extend(_section("Mismatch Codes", summary.mismatch_code_counts))
    lines.extend(["## Caveat", "", "Corpus summaries use redacted case bundles and do not contain raw source logs or provider rankings.", ""])
    return "\n".join(lines)


def _section(title: str, values: dict[str, int]) -> list[str]:
    lines = [f"## {title}", ""]
    if not values:
        lines.append("- None")
    else:
        for key, value in values.items():
            lines.append(f"- {key}: {value}")
    lines.append("")
    return lines
