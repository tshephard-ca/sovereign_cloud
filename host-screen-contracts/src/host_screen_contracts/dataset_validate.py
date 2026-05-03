from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from .dataset_model import DatasetManifest, manifest_cases, load_dataset_manifest
from .field_map import load_field_map
from .flow_extract import extract_transaction
from .models import BlockerCode
from .parse_trace import load_trace
from .privacy_report import generate_privacy_report
from .replay_driver import TraceReplayDriver
from .validate_trace import validate_trace

try:
    import jsonschema
except Exception:  # pragma: no cover - optional at runtime
    jsonschema = None


def _schema_root() -> Path:
    package_schemas = Path(__file__).resolve().parent / "schemas"
    if package_schemas.exists():
        return package_schemas
    return Path(__file__).resolve().parents[2] / "schemas"


def _validate_json_schema(instance: Any, schema_name: str) -> str | None:
    if jsonschema is None:
        return None
    schema_path = _schema_root() / schema_name
    if not schema_path.exists():
        return f"MISSING_SCHEMA:{schema_name}"
    try:
        jsonschema.validate(instance, json.loads(schema_path.read_text()))
        return None
    except Exception as exc:  # noqa: BLE001 - concise validation message
        return f"SCHEMA_INVALID:{schema_name}:{str(exc).splitlines()[0]}"


def validate_dataset_package(package_dir: str | Path, *, strict: bool = False) -> dict[str, Any]:
    root = Path(package_dir)
    blockers: list[str] = []
    warnings: list[str] = []
    manifest: DatasetManifest | None = None
    manifest_path = root / "manifest.yml"
    if not manifest_path.exists():
        return {
            "schema_version": "1.0",
            "ok": False,
            "blockers": ["MISSING_MANIFEST"],
            "warnings": [],
            "trace_count": 0,
        }
    try:
        manifest = load_dataset_manifest(root)
    except Exception as exc:  # noqa: BLE001 - adversarial packages should report, not crash
        return {
            "schema_version": "1.0",
            "ok": False,
            "blockers": [f"MANIFEST_INVALID:{str(exc).splitlines()[0]}"],
            "warnings": [],
            "trace_count": 0,
        }
    manifest_schema_error = _validate_json_schema(
        manifest.model_dump(mode="json", exclude_none=True),
        "dataset_manifest.schema.json",
    )
    if manifest_schema_error:
        blockers.append(manifest_schema_error)
    field_map = None
    if manifest.field_map:
        field_map_path = root / manifest.field_map
        if field_map_path.exists():
            try:
                field_map = load_field_map(field_map_path)
            except Exception as exc:  # noqa: BLE001 - keep invalid maps machine-readable
                blockers.append(f"FIELD_MAP_INVALID:{str(exc).splitlines()[0]}")
        else:
            blockers.append("MISSING_FIELD_MAP")
    cases = manifest_cases(manifest)
    for case_id, case in cases.items():
        trace_path = root / case.trace
        if not trace_path.exists():
            blockers.append(f"MISSING_TRACE:{case_id}")
            continue
        raw_lines = [line for line in trace_path.read_text().splitlines() if line.strip()]
        for line_number, line in enumerate(raw_lines, start=1):
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                blockers.append(f"{case_id}:TRACE_JSON_INVALID:{line_number}:{exc.msg}")
                continue
            schema_error = _validate_json_schema(data, "trace.schema.json")
            if schema_error:
                blockers.append(f"{case_id}:{schema_error}")
        try:
            events = load_trace(trace_path)
        except Exception as exc:  # noqa: BLE001 - keep validation reports machine-readable
            blockers.append(f"{case_id}:TRACE_PARSE_FAILED:{exc}")
            continue
        case_field_map = field_map.for_case(case_id) if field_map is not None else None
        result = validate_trace(events, strict=strict, field_map=case_field_map)
        warnings.extend(f"{case_id}:{warning}" for warning in result.warnings)
        blockers.extend(f"{case_id}:{blocker}" for blocker in result.blockers)
        if case_field_map is not None:
            extraction = extract_transaction(
                events,
                transaction_id=manifest.transaction_id,
                case_id=case_id,
                case_kind=case_id,
                field_map=case_field_map,
                strict=strict,
            )
            warnings.extend(f"{case_id}:extract:{warning}" for warning in extraction.contract.warnings)
            for blocker in extraction.contract.blockers:
                if "cancel" in case_id.lower() and blocker in {
                    BlockerCode.NO_INPUT_FIELDS.value,
                    BlockerCode.NO_FINAL_OUTPUT_FIELDS.value,
                }:
                    warnings.append(f"{case_id}:NON_CONTRACT_CANCEL_CASE:{blocker}")
                else:
                    blockers.append(f"{case_id}:extract:{blocker}")
            try:
                driver = TraceReplayDriver(events, extraction.contract)
                for step in extraction.replay_case.steps:
                    if driver.current_screen_hash() != step.expect_screen_hash:
                        blockers.append(f"{case_id}:REPLAY_START_HASH_MISMATCH")
                        break
                    next_hash = driver.apply(step.aid, step.inputs)
                    if next_hash != step.expect_next_screen_hash:
                        blockers.append(f"{case_id}:REPLAY_NEXT_HASH_MISMATCH")
                        break
                driver.assert_no_unexpected_transition()
            except Exception as exc:  # noqa: BLE001 - validation report should continue
                blockers.append(f"{case_id}:REPLAY_FAILED:{exc}")
            privacy = generate_privacy_report(events, case_field_map)
            if privacy["unredacted_sensitive_value_count"]:
                warnings.append(f"{case_id}:UNREDACTED_SENSITIVE_VALUES:{privacy['unredacted_sensitive_value_count']}")
    for case_id, rel_path in manifest.replay_cases.items():
        if not (root / rel_path).exists():
            blockers.append(f"MISSING_REPLAY_CASE:{case_id}")
    if manifest.maturity_level in {"L4", "L5"} and len(cases) < 2:
        warnings.append("MATURITY_LEVEL_EXPECTS_MULTI_CASE_PACKAGE")
    if manifest.maturity_level in {"L3", "L4", "L5", "L6"} and field_map is None:
        blockers.append("MATURITY_LEVEL_REQUIRES_FIELD_MAP")
    return {
        "schema_version": "1.0",
        "ok": not blockers,
        "package_id": manifest.package_id,
        "transaction_id": manifest.transaction_id,
        "maturity_level": manifest.maturity_level,
        "evidence_kind": manifest.evidence_kind,
        "actual_maturity_level": manifest.actual_maturity_level,
        "simulates_maturity_level": manifest.simulates_maturity_level,
        "trace_count": len(cases),
        "replay_case_count": len(manifest.replay_cases),
        "warnings": sorted(set(warnings), key=warnings.index),
        "blockers": sorted(set(blockers), key=blockers.index),
    }
