from __future__ import annotations

import json
from pathlib import Path


def test_schema_files_are_present_and_parseable():
    root = Path(__file__).resolve().parents[1] / "schemas"
    expected = {
        "envelope.schema.json",
        "summary.schema.json",
        "review_lane.schema.json",
        "action_queue.schema.json",
        "case_manifest.schema.json",
        "assessment_packet.schema.json",
        "cabinet_profile.schema.json",
        "scenario_manifest.schema.json",
        "manifest.schema.json",
        "explanation.schema.json",
    }
    assert expected == {path.name for path in root.glob("*.schema.json")}
    for name in expected:
        payload = json.loads((root / name).read_text(encoding="utf-8"))
        assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert payload["type"] == "object"
