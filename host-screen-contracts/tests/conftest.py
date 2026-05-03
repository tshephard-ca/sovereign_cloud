from __future__ import annotations

from pathlib import Path

import pytest

from host_screen_contracts.field_map import load_field_map
from host_screen_contracts.flow_extract import extract_transaction
from host_screen_contracts.parse_trace import load_trace


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


@pytest.fixture
def order_events():
    return load_trace(EXAMPLES / "order_lookup.trace.jsonl")


@pytest.fixture
def order_field_map():
    return load_field_map(EXAMPLES / "order_lookup.fields.yml")


@pytest.fixture
def order_result(order_events, order_field_map):
    def _extract(**kwargs):
        return extract_transaction(
            order_events,
            transaction_id="order_lookup",
            field_map=order_field_map,
            **kwargs,
        )

    return _extract


def build_order_result(**kwargs):
    return extract_transaction(
        load_trace(EXAMPLES / "order_lookup.trace.jsonl"),
        transaction_id="order_lookup",
        field_map=load_field_map(EXAMPLES / "order_lookup.fields.yml"),
        **kwargs,
    )
