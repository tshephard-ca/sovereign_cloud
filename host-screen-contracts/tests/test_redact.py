from __future__ import annotations

from pathlib import Path

from host_screen_contracts.field_map import load_field_map
from host_screen_contracts.flow_extract import extract_transaction
from host_screen_contracts.parse_trace import load_trace
from host_screen_contracts.redact import REDACTED, redact_value
from host_screen_contracts.field_map import FieldMap, FieldMapEntry
from host_screen_contracts.sanitize_trace import _replace_span, sanitize_trace_events
from host_screen_contracts.trace_schema import ActionEvent, NoteEvent, ScreenEvent

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


def test_sanitize_trace_handles_text_patterns_hidden_map_entries_and_notes():
    events = [
        ActionEvent(type="action", seq=1, aid="ENTER", inputs=[{"field_id": "password", "value": "secret"}]),
        ScreenEvent(type="screen", seq=2, rows=24, cols=80, text=["Account 12345678 token SECRET123456"], fields=[]),
        NoteEvent(type="note", seq=3, note="operator note"),
    ]
    field_map = FieldMap(
        fields=[
            FieldMapEntry(screen_ref="screen_002", row=1, col=9, length=8, name="account_number", role="output", sensitive=False),
            FieldMapEntry(screen_ref="screen_002", row=1, col=24, length=12, name="hidden_token", role="hidden", sensitive=True),
        ]
    )
    sanitized, report = sanitize_trace_events(events, field_map=field_map)

    assert sanitized[0]["inputs"][0]["value"] == REDACTED
    assert "12345678" in sanitized[1]["text"][0]
    assert REDACTED in sanitized[1]["text"][0]
    assert sanitized[2]["note"] == "operator note"
    assert report["unredacted_sensitive_value_count"] == 0
    assert _replace_span("abc", 0, 1, "x") == "abc"
