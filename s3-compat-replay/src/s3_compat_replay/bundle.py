from __future__ import annotations

import csv
import json
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .artifact_redaction import build_redaction_report, report_to_text, sanitize_artifact, sanitize_text
from .decision import build_cutover_brief, cutover_brief_markdown
from .models import CaseBundleManifest, FieldReview, ProbePlan, ProbeResults, RedactionReport, UsageProfile
from .probe_plan import plan_from_yaml, plan_to_yaml
from .questionnaire import generate_questionnaire, load_mismatches_csv, questionnaire_to_markdown
from .redact import Redactor, stable_hash
from .report import build_summary, read_json, summary_markdown


REQUIRED_BUNDLE_FILES = {
    "case.yml",
    "usage-profile.json",
    "probe-plan.yml",
    "redaction-report.json",
}


def create_case_bundle(
    *,
    profile_path: str | Path,
    plan_path: str | Path,
    output_path: str | Path,
    results_path: str | Path | None = None,
    mismatches_path: str | Path | None = None,
    summary_path: str | Path | None = None,
    markdown_path: str | Path | None = None,
    cleanup_manifest_path: str | Path | None = None,
    workload_type: str = "unspecified",
    shareable: bool = True,
) -> tuple[CaseBundleManifest, RedactionReport]:
    profile = UsageProfile(**read_json(profile_path))
    plan = plan_from_yaml(Path(plan_path).read_text(encoding="utf-8"))
    results = ProbeResults(**read_json(results_path)) if results_path else None
    mismatches = load_mismatches_csv(mismatches_path)
    summary = build_summary(profile, results, plan) if results else None

    redactor = Redactor()
    forbidden_terms = _forbidden_terms(profile, plan, results)
    sanitized_profile = sanitize_artifact(profile.model_dump(mode="json"), redactor=redactor, forbidden_terms=forbidden_terms)
    sanitized_plan = sanitize_artifact(plan.model_dump(mode="json"), redactor=redactor, forbidden_terms=forbidden_terms)
    sanitized_results = sanitize_artifact(results.model_dump(mode="json"), redactor=redactor, forbidden_terms=forbidden_terms) if results else None
    sanitized_summary = sanitize_artifact((summary.model_dump(mode="json") if summary else read_json(summary_path)), redactor=redactor, forbidden_terms=forbidden_terms) if summary or summary_path else None
    sanitized_mismatches = _sanitize_mismatch_rows(mismatches, redactor, forbidden_terms) if mismatches_path else []
    questionnaire = generate_questionnaire(UsageProfile(**sanitized_profile), mismatches)
    sanitized_questionnaire = sanitize_artifact(questionnaire.model_dump(mode="json"), redactor=redactor, forbidden_terms=forbidden_terms)
    brief = build_cutover_brief(profile, plan, results, summary or build_summary(profile, results, plan), business_context={}) if results else None
    sanitized_brief = sanitize_artifact(brief.model_dump(mode="json"), redactor=redactor, forbidden_terms=forbidden_terms) if brief else None
    field_review = FieldReview()

    artifacts: dict[str, Any] = {
        "usage-profile.json": sanitized_profile,
        "probe-plan.yml": yaml.safe_dump(sanitized_plan, sort_keys=False),
        "evidence/key-shapes.json": {"key_shapes": sanitized_profile.get("key_shapes", [])},
        "evidence/request-shapes.json": {"request_shapes": sanitized_profile.get("request_shapes", [])},
        "evidence/feature-evidence.json": _feature_evidence(sanitized_profile),
        "questionnaires/app-owner-questions.yml": yaml.safe_dump(sanitized_questionnaire, sort_keys=False),
        "questionnaires/app-owner-questions.md": sanitize_text(questionnaire_to_markdown(questionnaire), redactor=redactor, forbidden_terms=forbidden_terms),
        "questionnaires/app-owner-answers.yml": yaml.safe_dump({"schema_version": 1, "answers": []}, sort_keys=False),
        "questionnaires/field-review-notes.yml": yaml.safe_dump(field_review.model_dump(mode="json"), sort_keys=False),
    }
    if sanitized_results:
        artifacts["probe-results/target-001.json"] = sanitized_results
    if sanitized_mismatches:
        artifacts["mismatches/target-001.csv"] = _mismatches_csv_text(sanitized_mismatches)
    if sanitized_summary:
        artifacts["compat-summary.json"] = sanitized_summary
        if markdown_path:
            markdown_text = Path(markdown_path).read_text(encoding="utf-8")
        elif summary:
            markdown_text = summary_markdown(summary)
        else:
            markdown_text = "# Compatibility Preflight Summary\n\nSummary JSON was supplied without markdown.\n"
        artifacts["compat-summary.md"] = sanitize_text(markdown_text, redactor=redactor, forbidden_terms=forbidden_terms)
    if sanitized_brief and brief:
        artifacts["cutover-brief.json"] = sanitized_brief
        artifacts["cutover-brief.md"] = sanitize_text(cutover_brief_markdown(brief), redactor=redactor, forbidden_terms=forbidden_terms)
        artifacts["evidence/capability-ledger.json"] = {"capability_ledger": sanitized_brief.get("capability_ledger", [])}
    if cleanup_manifest_path and Path(cleanup_manifest_path).exists():
        artifacts["cleanup-manifest.json"] = sanitize_artifact(read_json(cleanup_manifest_path), redactor=redactor, forbidden_terms=forbidden_terms)

    manifest = CaseBundleManifest(
        case_id=_case_id(sanitized_profile),
        created_at=_now(),
        workload_type=workload_type,
        event_count_bucket=_event_count_bucket(int(sanitized_profile.get("event_count") or 0)),
        time_range_days=_time_range_days(sanitized_profile.get("time_range") or {}),
        observed_families=sorted((sanitized_profile.get("operation_families") or {}).keys()),
        evidence_sources=_evidence_sources(sanitized_profile),
        redaction_level="shareable" if shareable else "local",
        artifacts={name: name for name in sorted(artifacts)},
        business_outcome={"blocker_confirmed": None, "cutover_issue_prevented": None, "notes_redacted": True},
    )
    artifacts["case.yml"] = yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False)
    report = build_redaction_report(artifacts, forbidden_terms=forbidden_terms)
    artifacts["redaction-report.json"] = report_to_text(report)
    _write_bundle(output_path, artifacts)
    return manifest, report


def validate_case_bundle(path: str | Path, *, strict_redaction: bool = False) -> tuple[bool, list[str], RedactionReport]:
    artifacts = read_bundle_artifacts(path)
    errors: list[str] = []
    missing = sorted(REQUIRED_BUNDLE_FILES - set(artifacts))
    if missing:
        errors.append("missing required bundle files: " + ", ".join(missing))
    try:
        CaseBundleManifest(**yaml.safe_load(str(artifacts.get("case.yml", ""))) or {})
    except Exception as exc:
        errors.append(f"case.yml invalid: {exc}")
    try:
        UsageProfile(**json.loads(str(artifacts.get("usage-profile.json", "{}"))))
    except Exception as exc:
        errors.append(f"usage-profile.json invalid: {exc}")
    try:
        plan_from_yaml(str(artifacts.get("probe-plan.yml", "")))
    except Exception as exc:
        errors.append(f"probe-plan.yml invalid: {exc}")
    try:
        embedded_report = RedactionReport(**json.loads(str(artifacts.get("redaction-report.json", "{}"))))
    except Exception as exc:
        embedded_report = RedactionReport(redaction_status="FAIL", shareable=False, notes=[f"redaction-report.json invalid: {exc}"])
        errors.append(f"redaction-report.json invalid: {exc}")
    scan_report = build_redaction_report(artifacts)
    if embedded_report.redaction_status != "PASS":
        errors.append("embedded redaction report did not pass")
    if strict_redaction and scan_report.redaction_status != "PASS":
        errors.append("strict redaction scan failed")
    return not errors, errors, scan_report if scan_report.redaction_status != "PASS" else embedded_report


def read_bundle_artifacts(path: str | Path) -> dict[str, str]:
    target = Path(path)
    if target.is_dir():
        return {str(p.relative_to(target)): p.read_text(encoding="utf-8") for p in sorted(target.rglob("*")) if p.is_file()}
    artifacts: dict[str, str] = {}
    with zipfile.ZipFile(target) as archive:
        for name in sorted(archive.namelist()):
            if name.endswith("/"):
                continue
            artifacts[name] = archive.read(name).decode("utf-8")
    return artifacts


def zip_directory(source_dir: str | Path, output_path: str | Path) -> Path:
    source = Path(source_dir)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.writestr(str(path.relative_to(source)), path.read_bytes())
    return output


def materialize_bundle_to_temp(path: str | Path) -> Path:
    target = Path(path)
    temp = Path(tempfile.mkdtemp(prefix="s3-compat-replay-bundle-"))
    if target.is_dir():
        shutil.copytree(target, temp, dirs_exist_ok=True)
    else:
        with zipfile.ZipFile(target) as archive:
            archive.extractall(temp)
    return temp


def _write_bundle(output_path: str | Path, artifacts: dict[str, Any]) -> None:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() == ".zip":
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(artifacts):
                archive.writestr(name, _artifact_to_text(artifacts[name]))
    else:
        target.mkdir(parents=True, exist_ok=True)
        for name, payload in artifacts.items():
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_artifact_to_text(payload), encoding="utf-8")


def _artifact_to_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload if payload.endswith("\n") else payload + "\n"
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _sanitize_mismatch_rows(mismatches: list[Any], redactor: Redactor, forbidden_terms: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for mismatch in mismatches:
        row = mismatch.model_dump(mode="json")
        rows.append({key: sanitize_text(str(value), redactor=redactor, forbidden_terms=forbidden_terms) for key, value in row.items()})
    return rows


def _mismatches_csv_text(rows: list[dict[str, str]]) -> str:
    from .report import MISMATCH_COLUMNS
    import io

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=MISMATCH_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()


def _forbidden_terms(profile: UsageProfile, plan: ProbePlan, results: ProbeResults | None) -> list[str]:
    terms = [profile.source_bucket, plan.source_bucket]
    if results:
        terms.extend([results.target_bucket_redacted, results.endpoint_url_redacted])
    return sorted({term for term in terms if _is_forbidden_term(term)})


def _is_forbidden_term(term: str | None) -> bool:
    if not term:
        return False
    if term in {"bucket_001", "bucket_002", "bucket_003", "endpoint_redacted"}:
        return False
    if "endpoint_redacted" in term or term.endswith(".example.invalid"):
        return False
    return True


def _feature_evidence(profile_payload: dict[str, Any]) -> dict[str, Any]:
    family_features = {
        family: data.get("observed_features", [])
        for family, data in sorted((profile_payload.get("operation_families") or {}).items())
    }
    return {
        "observed_features": profile_payload.get("observed_features", []),
        "request_hint_features": profile_payload.get("request_hint_features", []),
        "bucket_config_features": profile_payload.get("bucket_config_features", []),
        "operation_family_features": family_features,
    }


def _case_id(profile_payload: dict[str, Any]) -> str:
    basis = json.dumps(
        {
            "source_bucket": profile_payload.get("source_bucket"),
            "event_count": profile_payload.get("event_count"),
            "families": sorted((profile_payload.get("operation_families") or {}).keys()),
            "time_range": profile_payload.get("time_range"),
        },
        sort_keys=True,
    )
    return f"case_{stable_hash(basis, 12)}"


def _event_count_bucket(count: int) -> str:
    if count < 1000:
        return "0_1k"
    if count < 100000:
        return "1k_100k"
    if count < 1000000:
        return "100k_1m"
    return "1m_plus"


def _time_range_days(time_range: dict[str, Any]) -> int | None:
    first = time_range.get("first_event_time")
    last = time_range.get("last_event_time")
    if not first or not last:
        return None
    try:
        start = datetime.fromisoformat(first.replace("Z", "+00:00"))
        end = datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max((end - start).days, 0)


def _evidence_sources(profile_payload: dict[str, Any]) -> list[str]:
    sources = set()
    if profile_payload.get("processed_event_count", 0) > 0:
        sources.add("CLOUDTRAIL")
    if profile_payload.get("request_hint_features"):
        sources.add("REQUEST_HINTS")
    if profile_payload.get("bucket_config_features"):
        sources.add("BUCKET_CONFIG")
    return sorted(sources)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
