from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from .models import AlignmentResult, CabinetEnvelope, EvidenceManifest, Summary
from .redact import Redactor
from .report import (
    redact_envelope,
    redact_summary,
    write_aligned_timeseries_csv,
    write_explanation_markdown,
    write_explanation_json,
    write_guardrail_markdown,
    write_json,
)


INPUT_FILENAMES = {
    "power": "pdu_power.csv",
    "temperature": "inlet_temps.csv",
    "cabinet_profile": "cabinet_profile.yml",
    "thresholds": "thresholds.yml",
}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint_inputs(paths: dict[str, Path | None]) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, path in sorted(paths.items()):
        if path and Path(path).exists():
            out[name] = sha256_file(path)
    return out


def write_evidence_bundle(
    output_dir: str | Path,
    envelope: CabinetEnvelope,
    summary: Summary,
    alignment: AlignmentResult,
    generated_at: datetime,
    input_paths: dict[str, Path | None],
    redact: bool = False,
) -> EvidenceManifest:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    redactor = Redactor()
    output_envelope = redact_envelope(envelope, redactor) if redact else envelope
    output_summary = redact_summary(summary, redactor) if redact else summary

    files = {
        "envelope": "envelope.json",
        "aligned_timeseries": "aligned_timeseries.csv",
        "sales_ops_guardrail": "sales_ops_guardrail.md",
        "summary": "summary.json",
        "explanation": "envelope_explanation.md",
        "explanation_json": "envelope_explanation.json",
        "input_fingerprints": "input_fingerprints.json",
        "manifest": "manifest.json",
    }
    write_json(root / files["envelope"], output_envelope)
    write_aligned_timeseries_csv(root / files["aligned_timeseries"], alignment, redact=redact, redactor=redactor)
    write_guardrail_markdown(root / files["sales_ops_guardrail"], output_envelope)
    write_json(root / files["summary"], output_summary)
    write_explanation_markdown(root / files["explanation"], output_envelope)
    write_explanation_json(root / files["explanation_json"], output_envelope)

    fingerprints = fingerprint_inputs(input_paths)
    write_json(root / files["input_fingerprints"], fingerprints)
    manifest = EvidenceManifest(
        generated_at=generated_at,
        cabinet_id=output_envelope.cabinet_id,
        bundle_type="redacted_evidence" if redact else "evidence",
        files=files,
        input_fingerprints=fingerprints,
        envelope_status=output_envelope.envelope_status,
        confidence=output_envelope.confidence,
        reason_codes=output_envelope.reason_codes,
        warnings=output_envelope.warnings,
        blockers=output_envelope.blockers,
    )
    write_json(root / files["manifest"], manifest)
    return manifest


def _redact_recursive(value: Any, redactor: Redactor) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key == "cabinet_id":
                out[key] = redactor.redact("cabinet", item)
            elif key == "display_name":
                out[key] = redactor.redact("display_name", item)
            elif key == "pdu_id":
                out[key] = redactor.redact("pdu", item)
            elif key == "sensor_id":
                out[key] = redactor.redact("sensor", item)
            elif key == "circuit_id":
                out[key] = redactor.redact("circuit", item)
            elif key == "source":
                out[key] = redactor.redact("source", item)
            else:
                out[key] = _redact_recursive(item, redactor)
        return out
    if isinstance(value, list):
        return [_redact_recursive(item, redactor) for item in value]
    return value


def redact_csv(input_path: Path, output_path: Path, redactor: Redactor) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open("r", encoding="utf-8", newline="") as src, output_path.open("w", encoding="utf-8", newline="") as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=reader.fieldnames or [])
        writer.writeheader()
        for row in reader:
            payload = dict(row)
            if "cabinet_id" in payload:
                payload["cabinet_id"] = redactor.redact("cabinet", payload["cabinet_id"])
            if "pdu_id" in payload:
                payload["pdu_id"] = redactor.redact("pdu", payload["pdu_id"])
            if "sensor_id" in payload:
                payload["sensor_id"] = redactor.redact("sensor", payload["sensor_id"])
            if "circuit_id" in payload:
                payload["circuit_id"] = redactor.redact("circuit", payload["circuit_id"])
            if "source" in payload:
                payload["source"] = redactor.redact("source", payload["source"])
            writer.writerow(payload)


def redact_yaml(input_path: Path, output_path: Path, redactor: Redactor) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    loaded = yaml.safe_load(input_path.read_text(encoding="utf-8")) or {}
    output_path.write_text(yaml.safe_dump(_redact_recursive(loaded, redactor), sort_keys=False), encoding="utf-8")


def redact_json(input_path: Path, output_path: Path, redactor: Redactor) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    loaded = json.loads(input_path.read_text(encoding="utf-8"))
    output_path.write_text(json.dumps(_redact_recursive(loaded, redactor), indent=2) + "\n", encoding="utf-8")


def redact_text(input_path: Path, output_path: Path, redactor: Redactor) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = input_path.read_text(encoding="utf-8")
    for mapping in redactor._maps.values():  # intentionally reuse stable bundle mapping
        for original, replacement in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
            text = text.replace(original, replacement)
    output_path.write_text(text, encoding="utf-8")


def redact_bundle(input_dir: str | Path, output_dir: str | Path) -> EvidenceManifest:
    source = Path(input_dir)
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    redactor = Redactor()
    files: dict[str, str] = {}
    fingerprints: dict[str, str] = {}

    for path in sorted(source.rglob("*")):
        if path.is_dir():
            continue
        relative = path.relative_to(source)
        output_path = target / relative
        fingerprints[str(relative)] = sha256_file(path)
        if path.suffix.lower() == ".csv":
            redact_csv(path, output_path, redactor)
        elif path.suffix.lower() in {".yml", ".yaml"}:
            redact_yaml(path, output_path, redactor)
        elif path.suffix.lower() == ".json":
            redact_json(path, output_path, redactor)
        elif path.suffix.lower() in {".md", ".txt"}:
            redact_text(path, output_path, redactor)
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, output_path)
        files[str(relative)] = str(relative)

    manifest = EvidenceManifest(
        generated_at=datetime.now().astimezone(),
        cabinet_id=redactor.redact("cabinet", source.name) or "cabinet_001",
        bundle_type="redacted_handoff",
        files=files,
        input_fingerprints=fingerprints,
    )
    write_json(target / "redaction_manifest.json", manifest)
    return manifest
