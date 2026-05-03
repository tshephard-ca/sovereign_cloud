from __future__ import annotations

from pathlib import Path

from host_screen_contracts.field_map import load_field_map
from host_screen_contracts.flow_extract import extract_transaction
from host_screen_contracts.parse_trace import load_trace
from host_screen_contracts.redact import REDACTED, redact_value

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_redaction_removes_sensitive_values_from_generated_replay_case():
    result = extract_transaction(
        load_trace(EXAMPLES / "customer_update.trace.jsonl"),
        transaction_id="customer_update",
        field_map=load_field_map(EXAMPLES / "customer_update.fields.yml"),
        redact=True,
    )
    inputs = result.replay_case.steps[0].inputs
    assert inputs["account_number"] == REDACTED
    assert inputs["phone"] == "5550100"


def test_redact_value_uses_sensitive_name_patterns():
    assert redact_value("secret-value", "api_token", None, redact=True) == REDACTED
    assert redact_value("public", "status", None, redact=True) == "public"
