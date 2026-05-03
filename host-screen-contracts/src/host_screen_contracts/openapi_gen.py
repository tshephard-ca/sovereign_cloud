from __future__ import annotations

import re
from typing import Any

from .contract_model import ScreenFieldContract, TransactionContract


def _schema_name(transaction_id: str, suffix: str) -> str:
    words = re.split(r"[^A-Za-z0-9]+", transaction_id)
    return "".join(word[:1].upper() + word[1:] for word in words if word) + suffix


def _field_schema(field: ScreenFieldContract) -> dict[str, Any]:
    screen_field = _field_origin(field)
    schema: dict[str, Any] = {
        "type": field.type,
        "x-screen-field": screen_field,
        "x-field-confidence": field.confidence.value,
        "x-inference-source": field.inference_source,
    }
    if field.pattern:
        schema["pattern"] = field.pattern
    if field.format:
        schema["format"] = field.format
    if field.description:
        schema["description"] = field.description
    return schema


def _field_origin(field: ScreenFieldContract) -> dict[str, Any]:
    origin: dict[str, Any] = {
        "screen_ref": field.screen_ref,
        "row": field.row,
        "col": field.col,
        "length": field.length,
        "confidence": field.confidence.value.lower(),
        "role": field.role,
    }
    if field.field_id:
        origin["field_id"] = field.field_id
    return origin


def _schema_properties(fields: list[ScreenFieldContract]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for field in fields:
        if field.name not in properties:
            properties[field.name] = _field_schema(field)
            continue
        existing = properties[field.name]
        existing.setdefault("x-alternate-screen-fields", []).append(_field_origin(field))
        existing["x-field-variant-review-required"] = True
    return properties


def generate_openapi(contract: TransactionContract) -> dict[str, Any]:
    request_name = _schema_name(contract.transaction_id, "Request")
    response_name = _schema_name(contract.transaction_id, "Response")
    error_name = _schema_name(contract.transaction_id, "Error")
    request_required = [field.name for field in contract.request_fields if field.required]
    error_fields = [field for field in contract.response_fields if field.role == "error_message"]
    has_error_schema = bool(error_fields) or "ERROR_SCREEN_RECORDED" in contract.warnings
    flow = [
        {
            "from_screen_ref": transition.from_screen_ref,
            "aid": transition.aid,
            "to_screen_ref": transition.to_screen_ref,
            "expected_to_screen_hash": transition.expected_to_screen_hash,
        }
        for transition in contract.transitions
    ]
    subfile_regions = [
        {"screen_ref": screen.screen_ref, "screen_hash": screen.screen_hash, **region}
        for screen in contract.screens
        for region in screen.subfile_regions
    ]
    responses: dict[str, Any] = {
        "200": {
            "description": "Successful transaction response",
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{response_name}"}
                }
            },
        },
        "409": {"description": "Screen flow did not match the expected contract"},
        "422": {"description": "Input failed validation or screen returned an error state"},
    }
    if has_error_schema:
        responses["422"]["content"] = {
            "application/json": {
                "schema": {"$ref": f"#/components/schemas/{error_name}"}
            }
        }
    schemas: dict[str, Any] = {
        request_name: {
            "type": "object",
            "required": request_required,
            "properties": _schema_properties(contract.request_fields),
        },
        response_name: {
            "type": "object",
            "properties": _schema_properties([field for field in contract.response_fields if field.role != "error_message"]),
        },
    }
    if has_error_schema:
        properties = {
            "message": {
                "type": "string",
                "description": "Recorded host screen error or message text.",
            }
        }
        properties.update(_schema_properties(error_fields))
        schemas[error_name] = {
            "type": "object",
            "properties": properties,
            "x-error-source": "recorded_screen_trace",
        }

    operation_extensions: dict[str, Any] = {
        "x-screen-flow": flow,
        "x-contract-confidence": contract.confidence.value,
        "x-source-screen-hash": contract.screens[0].screen_hash if contract.screens else "",
        "x-generated-by": "host-screen-contracts",
    }
    if subfile_regions:
        operation_extensions["x-subfile-regions"] = subfile_regions
    if contract.flow_graph:
        operation_extensions["x-screen-flow-graph"] = {
            "node_count": contract.flow_graph.get("node_count", 0),
            "edge_count": contract.flow_graph.get("edge_count", 0),
            "case_count": contract.flow_graph.get("case_count", 0),
        }

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Host Screen Transaction API",
            "version": "0.1.0",
        },
        "paths": {
            contract.endpoint_path: {
                "post": {
                    "operationId": contract.transaction_id,
                    "summary": f"Execute recorded transaction: {contract.display_name}",
                    **operation_extensions,
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": f"#/components/schemas/{request_name}"}
                            }
                        },
                    },
                    "responses": responses,
                }
            }
        },
        "components": {
            "schemas": schemas
        },
    }
