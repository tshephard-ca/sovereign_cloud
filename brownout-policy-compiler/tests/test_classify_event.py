from __future__ import annotations

from brownout_policy_compiler.classify_event import classify_attack_context
from brownout_policy_compiler.event_schema import load_event


def test_classifies_volumetric_event(examples):
    assert classify_attack_context(load_event(examples / "events" / "volumetric_event.json")) == "volumetric"


def test_classifies_application_event(examples):
    assert classify_attack_context(load_event(examples / "events" / "app_layer_event.json")) == "application"

