from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any

import yaml


def validate_openapi_document(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if document.get("openapi") != "3.1.0":
        errors.append("OPENAPI_VERSION_NOT_3_1_0")
    info = document.get("info")
    if not isinstance(info, dict) or not info.get("title") or not info.get("version"):
        errors.append("OPENAPI_INFO_INVALID")
    paths = document.get("paths")
    if not isinstance(paths, dict) or not paths:
        errors.append("OPENAPI_PATHS_MISSING")
        return errors
    schemas = document.get("components", {}).get("schemas", {})
    if not isinstance(schemas, dict) or not schemas:
        errors.append("OPENAPI_SCHEMAS_MISSING")
    for path, path_item in paths.items():
        if not isinstance(path, str) or not path.startswith("/"):
            errors.append(f"OPENAPI_PATH_INVALID:{path}")
        if not isinstance(path_item, dict) or "post" not in path_item:
            errors.append(f"OPENAPI_POST_MISSING:{path}")
            continue
        operation = path_item["post"]
        if not operation.get("operationId"):
            errors.append(f"OPENAPI_OPERATION_ID_MISSING:{path}")
        if not operation.get("summary"):
            errors.append(f"OPENAPI_SUMMARY_MISSING:{path}")
        if operation.get("x-generated-by") != "host-screen-contracts":
            errors.append(f"OPENAPI_GENERATOR_METADATA_MISSING:{path}")
        flow = operation.get("x-screen-flow")
        if not isinstance(flow, list):
            errors.append(f"OPENAPI_SCREEN_FLOW_MISSING:{path}")
        else:
            for index, transition in enumerate(flow):
                if not all(transition.get(key) for key in ("from_screen_ref", "aid", "to_screen_ref", "expected_to_screen_hash")):
                    errors.append(f"OPENAPI_SCREEN_FLOW_INVALID:{path}:{index}")
        responses = operation.get("responses", {})
        for status in ("200", "409", "422"):
            if status not in responses:
                errors.append(f"OPENAPI_RESPONSE_MISSING:{path}:{status}")
        request_ref = (
            operation.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
            .get("$ref")
        )
        response_ref = (
            operation.get("responses", {})
            .get("200", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
            .get("$ref")
        )
        for label, ref in (("request", request_ref), ("response", response_ref)):
            if not ref or not ref.startswith("#/components/schemas/"):
                errors.append(f"OPENAPI_{label.upper()}_REF_MISSING:{path}")
                continue
            schema_name = ref.rsplit("/", 1)[-1]
            if schema_name not in schemas:
                errors.append(f"OPENAPI_{label.upper()}_REF_UNKNOWN:{schema_name}")
            else:
                _validate_schema(schema_name, schemas[schema_name], errors)
        error_ref = (
            responses.get("422", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
            .get("$ref")
        )
        if error_ref:
            if not error_ref.startswith("#/components/schemas/"):
                errors.append(f"OPENAPI_ERROR_REF_INVALID:{path}")
            else:
                error_schema_name = error_ref.rsplit("/", 1)[-1]
                if error_schema_name not in schemas:
                    errors.append(f"OPENAPI_ERROR_REF_UNKNOWN:{error_schema_name}")
                else:
                    _validate_schema(error_schema_name, schemas[error_schema_name], errors, require_screen_fields=False)
    return errors


def _validate_schema(
    schema_name: str,
    schema: dict[str, Any],
    errors: list[str],
    *,
    require_screen_fields: bool = True,
) -> None:
    if schema.get("type") != "object":
        errors.append(f"OPENAPI_SCHEMA_TYPE_INVALID:{schema_name}")
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        errors.append(f"OPENAPI_SCHEMA_PROPERTIES_INVALID:{schema_name}")
        return
    required = schema.get("required", [])
    if required and not isinstance(required, list):
        errors.append(f"OPENAPI_SCHEMA_REQUIRED_INVALID:{schema_name}")
    for field_name in required:
        if field_name not in properties:
            errors.append(f"OPENAPI_REQUIRED_FIELD_UNKNOWN:{schema_name}:{field_name}")
    for field_name, field_schema in properties.items():
        if not isinstance(field_schema, dict):
            errors.append(f"OPENAPI_FIELD_SCHEMA_INVALID:{schema_name}:{field_name}")
            continue
        if field_schema.get("type") not in {"string", "integer", "number", "boolean", "object", "array"}:
            errors.append(f"OPENAPI_FIELD_TYPE_INVALID:{schema_name}:{field_name}")
        screen_field = field_schema.get("x-screen-field")
        if require_screen_fields and screen_field is None:
            errors.append(f"OPENAPI_SCREEN_FIELD_METADATA_MISSING:{schema_name}:{field_name}")
        if screen_field is not None:
            for key in ("screen_ref", "row", "col", "length", "confidence"):
                if key not in screen_field:
                    errors.append(f"OPENAPI_SCREEN_FIELD_METADATA_INVALID:{schema_name}:{field_name}:{key}")
        if require_screen_fields and "x-field-confidence" not in field_schema:
            errors.append(f"OPENAPI_FIELD_CONFIDENCE_MISSING:{schema_name}:{field_name}")
        if require_screen_fields and "x-inference-source" not in field_schema:
            errors.append(f"OPENAPI_INFERENCE_SOURCE_MISSING:{schema_name}:{field_name}")


def validate_openapi_file(path: str | Path) -> list[str]:
    document = yaml.safe_load(Path(path).read_text()) or {}
    if not isinstance(document, dict):
        return ["OPENAPI_DOCUMENT_NOT_OBJECT"]
    return validate_openapi_document(document)


def run_external_openapi_validator(path: str | Path, command: str | list[str] | None, *, timeout_seconds: int = 30) -> dict[str, Any]:
    if not command:
        return {"skipped": True}
    args = shlex.split(command) if isinstance(command, str) else list(command)
    openapi_path = str(path)
    if "{openapi}" in args:
        args = [openapi_path if arg == "{openapi}" else arg for arg in args]
    else:
        args.append(openapi_path)
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        return {
            "skipped": False,
            "ok": False,
            "command": args,
            "exit_code": None,
            "stdout": "",
            "stderr": str(exc),
            "error": "EXTERNAL_VALIDATOR_NOT_FOUND",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "skipped": False,
            "ok": False,
            "command": args,
            "exit_code": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "error": "EXTERNAL_VALIDATOR_TIMEOUT",
        }
    return {
        "skipped": False,
        "ok": completed.returncode == 0,
        "command": args,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
