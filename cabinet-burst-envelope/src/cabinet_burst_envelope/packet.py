from __future__ import annotations

from pathlib import Path

from .analysis import CabinetAnalysisResult
from .bundle import write_evidence_bundle
from .models import ActionQueue, EvidenceManifest, ReviewLaneDecision
from .redact import Redactor
from .report import _redact_nested_ids, redact_envelope, render_guardrail_markdown, write_json
from .worksheet import render_facility_review_worksheet


def write_assessment_packet(
    output_dir: str | Path,
    result: CabinetAnalysisResult,
    input_paths: dict[str, Path | None],
    redact: bool = False,
) -> EvidenceManifest:
    root = Path(output_dir)
    manifest = write_evidence_bundle(
        root,
        result.envelope,
        result.summary,
        result.alignment,
        result.generated_at,
        input_paths,
        redact=redact,
    )
    review_lane = result.review_lane
    packet_envelope = result.envelope
    if redact:
        redactor = Redactor()
        packet_envelope = redact_envelope(result.envelope, redactor)
        review_lane = ReviewLaneDecision.model_validate(_redact_nested_ids(result.review_lane.model_dump(mode="python"), redactor))
    action_queue = ActionQueue(
        cabinet_id=review_lane.cabinet_id,
        review_lane=review_lane.lane,
        actions=review_lane.next_actions,
    )
    files = dict(manifest.files)
    files.update(
        {
            "decision": "decision.json",
            "action_queue": "action_queue.json",
            "cabinet_review_packet": "cabinet_review_packet.md",
            "facility_review_worksheet": "facility_review_worksheet.md",
        }
    )
    write_json(root / files["decision"], review_lane)
    write_json(root / files["action_queue"], action_queue)
    (root / files["cabinet_review_packet"]).write_text(render_guardrail_markdown(packet_envelope), encoding="utf-8")
    (root / files["facility_review_worksheet"]).write_text(render_facility_review_worksheet(packet_envelope), encoding="utf-8")

    manifest.bundle_type = "redacted_assessment_packet" if redact else "assessment_packet"
    manifest.files = files
    write_json(root / files["manifest"], manifest)
    return manifest
