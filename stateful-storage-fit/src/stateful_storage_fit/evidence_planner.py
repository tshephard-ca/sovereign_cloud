from __future__ import annotations

from .classify_processes import ProcessClassification
from .models import CandidateDataMount, EvidenceQuestion, FitResult, StorageBehaviorFingerprint


def plan_evidence_questions(
    *,
    fit_result: FitResult,
    candidates: list[CandidateDataMount],
    process_info: ProcessClassification,
    fingerprint: StorageBehaviorFingerprint,
) -> list[EvidenceQuestion]:
    questions: list[EvidenceQuestion] = []

    def add(
        id_: str,
        priority: str,
        question: str,
        why: str,
        would_change: list[str],
        codes: list[str],
        evidence: list[str],
    ) -> None:
        if not any(item.id == id_ for item in questions):
            questions.append(
                EvidenceQuestion(
                    id=id_,
                    priority=priority,
                    question=question,
                    why_it_matters=why,
                    would_change=would_change,
                    related_reason_codes=codes,
                    suggested_local_evidence=evidence,
                )
            )

    if "candidate_data_mount" in fit_result.missing_data:
        add(
            "identify_data_paths",
            "HIGH",
            "Which filesystem paths contain durable application data?",
            "No candidate data mount was identified, so the storage request and access pattern may be wrong.",
            ["storage_request_gib", "required_access_mode", "preferred_storage_kind"],
            ["DATA_MOUNT_DETECTED"],
            ["Run df -PT -B1 and provide --data-path for known application data paths.", "Optionally provide du summaries for those paths."],
        )
    if "ROOT_ONLY_STORAGE_VIEW" in fit_result.reason_codes:
        add(
            "root_filesystem_data_scope",
            "HIGH",
            "Is durable application data actually stored on /, and which subpaths are stateful?",
            "Root-only storage visibility lowers confidence and can hide multiple logical data stores.",
            ["storage_request_gib", "capacity_risk", "preferred_storage_kind"],
            ["ROOT_ONLY_STORAGE_VIEW"],
            ["Run df -PT -B1 and pass --data-path for durable application directories."],
        )
    if "SHARED_FS_DETECTED" in fit_result.reason_codes:
        add(
            "shared_filesystem_semantics",
            "HIGH",
            "Why is the shared filesystem mounted, and does the workload require concurrent writers?",
            "RWX may be a hard requirement, but some shared mounts are read-only content or operational convenience.",
            ["required_access_mode", "preferred_storage_kind", "fit_status"],
            ["SHARED_FS_DETECTED", "RWX_REQUIRED"],
            ["Review mount options and application ownership of the shared path.", "Collect process owners that read/write the shared path."],
        )
    if process_info.file_server_processes:
        add(
            "file_server_access_pattern",
            "HIGH",
            "Is this workload itself a file-serving system, and what are the client read/write semantics?",
            "File-serving processes can imply architecture-level storage constraints that mount data alone cannot prove.",
            ["writer_topology", "required_access_mode", "fit_status"],
            ["FILE_SERVER_PROCESS_DETECTED", "HUMAN_ARCHITECTURE_REVIEW_REQUIRED"],
            ["Confirm whether clients write concurrently and whether file locking is required."],
        )
    if process_info.raw_block_hint:
        add(
            "raw_block_confirmation",
            "HIGH",
            "Is a raw block device truly required, or is the device reference part of normal filesystem-backed storage?",
            "Raw Block volume mode should not be inferred casually; this fact can change PASS/FAIL.",
            ["required_volume_mode", "fit_status"],
            ["RAW_BLOCK_HINT", "RAW_BLOCK_REVIEW_REQUIRED"],
            ["Collect lsblk --json, blkid, and application storage configuration snippets with secrets removed."],
        )
    if "iostat" in fit_result.missing_data:
        add(
            "collect_iostat",
            "MEDIUM",
            "Can a short extended iostat sample be provided for the workload during normal activity?",
            "Without iostat, latency risk and performance tier selection remain weak.",
            ["latency_risk", "required_performance_tier", "recommended_storage_class"],
            ["IOSTAT_MISSING"],
            ["Run iostat -x -d -m 1 5 during a representative period."],
        )
    if fit_result.latency_risk == "HIGH":
        add(
            "deeper_latency_validation",
            "HIGH",
            "Is the observed high await or utilization representative of normal workload behavior?",
            "A short iostat sample is not a benchmark, but high observed latency risk can change the required performance tier and review depth.",
            ["required_performance_tier", "recommended_storage_class", "fit_status"],
            ["LATENCY_RISK_HIGH", "FAST_STORAGE_RECOMMENDED"],
            [
                "Collect a longer iostat window during representative activity.",
                "If deeper validation is needed, design an explicit storage test separately; do not infer target performance from this sample.",
            ],
        )
    if "iostat_device_mapping" in fit_result.missing_data:
        add(
            "resolve_device_mapping",
            "HIGH",
            "Which block device backs each candidate data mount?",
            "Unclear device lineage can attach the wrong latency evidence to a data mount.",
            ["latency_risk", "required_performance_tier", "confidence"],
            ["IOSTAT_DEVICE_MAPPING_UNCERTAIN"],
            ["Run lsblk --json and findmnt --json.", "For LVM, collect pvs, vgs, and lvs."],
        )
    if fit_result.capacity_risk in {"MEDIUM", "HIGH"}:
        add(
            "capacity_growth_expectation",
            "MEDIUM",
            "What is the expected near-term growth rate for the candidate data paths?",
            "Capacity headroom is heuristic; growth expectations can change required size and expansion preference.",
            ["storage_request_gib", "capacity_risk", "recommended_storage_class"],
            [f"CAPACITY_RISK_{fit_result.capacity_risk}"],
            ["Collect recent filesystem growth if available.", "Confirm whether online expansion is required."],
        )
    if fingerprint.topology_sensitivity.value == "unknown":
        add(
            "topology_requirement",
            "LOW",
            "Does the workload require node-local persistence or zone-specific placement?",
            "VM evidence alone does not reveal platform scheduling and topology constraints.",
            ["preferred_storage_kind", "fit_status"],
            [],
            ["Ask the platform owner whether storage classes are topology-constrained."],
        )

    priority_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    return sorted(questions, key=lambda item: (priority_rank.get(item.priority, 9), item.id))
