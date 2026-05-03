from __future__ import annotations

import sys

import yaml

from host_screen_contracts.field_map import load_field_map
from host_screen_contracts.flow_extract import extract_transaction
from host_screen_contracts.openapi_gen import generate_openapi
from host_screen_contracts.openapi_validate import run_external_openapi_validator, validate_openapi_document
from host_screen_contracts.parse_trace import load_trace
from host_screen_contracts.real_world_data_generator import generate_real_world_corpus


def test_openapi_yaml_contains_openapi_31(order_result):
    doc = generate_openapi(order_result().contract)
    assert doc["openapi"] == "3.1.0"


def test_openapi_request_schema_contains_expected_request_field(order_result):
    doc = generate_openapi(order_result().contract)
    request_schema = doc["components"]["schemas"]["OrderLookupRequest"]
    assert "order_number" in request_schema["properties"]
    assert request_schema["required"] == ["order_number"]


def test_openapi_response_schema_contains_expected_response_fields(order_result):
    doc = generate_openapi(order_result().contract)
    response_schema = doc["components"]["schemas"]["OrderLookupResponse"]
    assert set(response_schema["properties"]) == {"customer_name", "order_status"}


def test_openapi_includes_screen_field_metadata(order_result):
    doc = generate_openapi(order_result().contract)
    field = doc["components"]["schemas"]["OrderLookupRequest"]["properties"]["order_number"]
    assert field["x-screen-field"]["screen_ref"] == "screen_001"
    assert field["x-field-confidence"] == "HIGH"


def test_openapi_structural_validator_catches_broken_refs(order_result):
    doc = generate_openapi(order_result().contract)
    assert validate_openapi_document(doc) == []
    post = next(iter(doc["paths"].values()))["post"]
    post["requestBody"]["content"]["application/json"]["schema"]["$ref"] = "#/components/schemas/Missing"
    assert validate_openapi_document(doc) == ["OPENAPI_REQUEST_REF_UNKNOWN:Missing"]


def test_optional_external_openapi_validator_runs_local_command(tmp_path, order_result):
    openapi_path = tmp_path / "openapi.yml"
    openapi_path.write_text(yaml.safe_dump(generate_openapi(order_result().contract), sort_keys=False))
    result = run_external_openapi_validator(openapi_path, [sys.executable, "-c", "import sys; sys.exit(0)"])
    assert result["ok"] is True
    assert result["command"][-1] == str(openapi_path)


def test_openapi_includes_error_schema_for_recorded_error_path(tmp_path):
    root = tmp_path / "corpus"
    generate_real_world_corpus(root)
    package = root / "synthetic_exception_paths"
    result = extract_transaction(
        load_trace(package / "traces/validation_error.trace.jsonl"),
        transaction_id="access_review",
        case_id="validation_error",
        case_kind="validation_error",
        field_map=load_field_map(package / "field_maps/transaction.fields.yml"),
    )
    doc = generate_openapi(result.contract)
    post = next(iter(doc["paths"].values()))["post"]

    assert "content" in post["responses"]["422"]
    assert "AccessReviewError" in doc["components"]["schemas"]
    assert "message_text" in doc["components"]["schemas"]["AccessReviewError"]["properties"]
    assert validate_openapi_document(doc) == []
