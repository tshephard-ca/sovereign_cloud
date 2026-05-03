from __future__ import annotations

from .models import QualificationResult


READINESS_LANES = [
    "MULTINODE_READY",
    "SINGLE_NODE_READY",
    "INFERENCE_ONLY",
    "AVOID_MULTINODE",
    "REVIEW_REQUIRED",
    "QUARANTINE_REVIEW",
]


def readiness_lane(result: QualificationResult) -> str:
    if result.qualification_status == "PASS":
        return "MULTINODE_READY"
    if result.qualification_status == "AVOID_MULTINODE":
        return "AVOID_MULTINODE"
    if result.qualification_status == "INFERENCE_ONLY":
        return "INFERENCE_ONLY"
    if result.qualification_status == "QUARANTINE":
        return "QUARANTINE_REVIEW"
    if "gpu_training_single_node_ok" in result.slurm_features:
        return "SINGLE_NODE_READY"
    return "REVIEW_REQUIRED"


def readiness_lane_counts(results: list[QualificationResult]) -> dict[str, int]:
    counts = {lane: 0 for lane in READINESS_LANES}
    for result in results:
        counts[readiness_lane(result)] += 1
    return counts


def business_risk(result: QualificationResult) -> str:
    lane = readiness_lane(result)
    if lane == "MULTINODE_READY":
        return "Candidate for normal multi-node training placement from supplied evidence."
    if lane == "SINGLE_NODE_READY":
        return "May be usable for single-node work, but broad scheduling needs review."
    if lane == "INFERENCE_ONLY":
        return "Multi-node training release is blocked by missing or incomplete evidence."
    if lane == "AVOID_MULTINODE":
        return "Could waste or stall distributed training if scheduled as fully ready."
    if lane == "QUARANTINE_REVIEW":
        return "Should remain out of normal scheduling until blockers are reviewed."
    return "Evidence or warnings require human review before broad scheduling."


def release_lane_description(lane: str) -> str:
    return {
        "MULTINODE_READY": "candidate for multi-node training, single-node training, and inference",
        "SINGLE_NODE_READY": "candidate for single-node work after review",
        "INFERENCE_ONLY": "candidate for inference only if site policy allows",
        "AVOID_MULTINODE": "avoid multi-node training placement",
        "REVIEW_REQUIRED": "human review required before broad scheduling",
        "QUARANTINE_REVIEW": "review before normal scheduling",
    }.get(lane, "human review required")
