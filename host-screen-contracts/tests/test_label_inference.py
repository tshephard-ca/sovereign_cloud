from __future__ import annotations

from host_screen_contracts.label_inference import detect_function_keys, infer_label, snake_case
from host_screen_contracts.trace_schema import ScreenEvent, TraceField


def test_label_inference_converts_nearby_labels_to_snake_case():
    screen = ScreenEvent(
        type="screen",
        seq=1,
        rows=24,
        cols=80,
        text=["   Order number . . . . . . . .  ________"],
        fields=[TraceField(id="f_01_32", row=1, col=32, length=8)],
    )
    inferred = infer_label(screen, screen.fields[0])
    assert inferred.name == "order_number"
    assert inferred.confidence == "MEDIUM"


def test_label_inference_uses_coordinate_name_when_no_label():
    screen = ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["                               VALUE"], fields=[TraceField(row=1, col=32, length=5)])
    assert infer_label(screen, screen.fields[0]).name == "field_01_32"


def test_snake_case_removes_filler():
    assert snake_case("Update Status") == "update_status"


def test_function_keys_are_detected_as_metadata():
    screen = ScreenEvent(type="screen", seq=1, rows=24, cols=80, text=["F3=Exit   F12=Cancel"])
    assert detect_function_keys(screen) == ["F3", "F12"]
