from __future__ import annotations

import pytest
from pydantic import ValidationError

from brownout_policy_compiler.event_schema import load_event

from .conftest import write_json


def test_valid_normalized_ddos_event_parses(examples):
    event = load_event(examples / "events" / "ddos_event.json")
    assert event.event_id == "evt-2026-001"
    assert len(event.targets) == 2


def test_invalid_ip_fails_validation_in_strict_mode(tmp_path, mutable_event):
    mutable_event["targets"][0]["ip"] = "not-an-ip"
    path = write_json(tmp_path / "event.json", mutable_event)
    with pytest.raises(ValidationError):
        load_event(path)


def test_invalid_port_fails_validation(tmp_path, mutable_event):
    mutable_event["targets"][0]["ports"] = [0]
    path = write_json(tmp_path / "event.json", mutable_event)
    with pytest.raises(ValidationError):
        load_event(path)

