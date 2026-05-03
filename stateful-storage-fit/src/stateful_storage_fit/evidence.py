from __future__ import annotations

from typing import Any

from .classify_mounts import is_network_fs
from .classify_processes import ProcessClassification
from .models import CandidateDataMount, EvidenceGraph, EvidenceInference, EvidenceObservation, IoDeviceSample


class _EvidenceBuilder:
    def __init__(self) -> None:
        self._obs_index = 0
        self._inf_index = 0
        self.observations: list[EvidenceObservation] = []
        self.inferences: list[EvidenceInference] = []

    def observation(
        self,
        *,
        kind: str,
        source: str,
        subject: str,
        value: Any = None,
        confidence: str = "MEDIUM",
        supports: list[str] | None = None,
        notes: list[str] | None = None,
    ) -> str:
        self._obs_index += 1
        obs_id = f"obs_{self._obs_index:04d}"
        self.observations.append(
            EvidenceObservation(
                id=obs_id,
                kind=kind,
                source=source,
                subject=subject,
                value=value,
                confidence=confidence,
                supports=supports or [],
                notes=notes or [],
            )
        )
        return obs_id

    def inference(
        self,
        *,
        kind: str,
        statement: str,
        confidence: str = "MEDIUM",
        evidence_ids: list[str] | None = None,
        requirement_fields: list[str] | None = None,
        notes: list[str] | None = None,
    ) -> str:
        self._inf_index += 1
        inf_id = f"inf_{self._inf_index:04d}"
        self.inferences.append(
            EvidenceInference(
                id=inf_id,
                kind=kind,
                statement=statement,
                confidence=confidence,
                evidence_ids=evidence_ids or [],
                requirement_fields=requirement_fields or [],
                notes=notes or [],
            )
        )
        return inf_id


def build_evidence_graph(
    *,
    candidates: list[CandidateDataMount],
    process_info: ProcessClassification,
    iostat_samples: dict[str, IoDeviceSample],
    missing_data: list[str],
    parse_warnings: list[str],
    fit_reason_codes: list[str],
    extra_evidence: dict[str, Any] | None = None,
) -> EvidenceGraph:
    builder = _EvidenceBuilder()
    data_mount_obs: list[str] = []
    shared_obs: list[str] = []
    latency_obs: list[str] = []

    for candidate in candidates:
        obs_id = builder.observation(
            kind="mount.candidate_data",
            source="df+mount+fstab",
            subject=candidate.mount_path,
            value={
                "source": candidate.source,
                "fs_type": candidate.fs_type,
                "used_gib": candidate.used_gib,
                "capacity_used_pct": candidate.capacity_used_pct,
                "reason": candidate.data_mount_reason,
            },
            confidence="HIGH" if candidate.data_mount_reason != "ROOT_ONLY_STORAGE_VIEW" else "MEDIUM",
            supports=["DATA_MOUNT_DETECTED"],
        )
        data_mount_obs.append(obs_id)
        if is_network_fs(candidate.fs_type):
            shared_obs.append(
                builder.observation(
                    kind="filesystem.shared_or_network",
                    source="mount+fstab",
                    subject=candidate.mount_path,
                    value={"fs_type": candidate.fs_type, "source": candidate.source},
                    confidence="HIGH",
                    supports=["SHARED_FS_DETECTED", "RWX_REQUIRED", "FILE_STORAGE_REQUIRED"],
                )
            )
        if candidate.latency_risk in {"MEDIUM", "HIGH"}:
            latency_obs.append(
                builder.observation(
                    kind="iostat.latency_risk",
                    source="iostat",
                    subject=candidate.device_from_iostat or candidate.source,
                    value={
                        "latency_risk": candidate.latency_risk,
                        "await_ms": candidate.await_ms,
                        "util_pct": candidate.util_pct,
                    },
                    confidence="MEDIUM",
                    supports=[f"LATENCY_RISK_{candidate.latency_risk}"],
                    notes=["Short iostat samples identify risk; they are not target-platform benchmarks."],
                )
            )

    for process in process_info.database_processes:
        builder.observation(
            kind="process.database_like",
            source="ps",
            subject=process,
            value=True,
            confidence="MEDIUM",
            supports=["DB_PROCESS_DETECTED", "BLOCK_STORAGE_PREFERRED"],
        )
    for process in process_info.stateful_processes:
        builder.observation(
            kind="process.stateful_service",
            source="ps",
            subject=process,
            value=True,
            confidence="MEDIUM",
            supports=["STATEFUL_PROCESS_DETECTED", "BLOCK_STORAGE_PREFERRED"],
        )
    for process in process_info.file_server_processes:
        builder.observation(
            kind="process.file_server",
            source="ps",
            subject=process,
            value=True,
            confidence="MEDIUM",
            supports=["FILE_SERVER_PROCESS_DETECTED", "HUMAN_ARCHITECTURE_REVIEW_REQUIRED"],
        )

    if process_info.raw_block_required or process_info.raw_block_hint:
        builder.observation(
            kind="process.raw_device_reference",
            source="ps",
            subject="process_args",
            value={"raw_block_required": process_info.raw_block_required, "raw_block_hint": process_info.raw_block_hint},
            confidence="HIGH" if process_info.raw_block_required else "LOW",
            supports=["RAW_BLOCK_HINT"],
        )

    for device, sample in sorted(iostat_samples.items()):
        builder.observation(
            kind="iostat.device_sample",
            source="iostat",
            subject=device,
            value={
                "await_ms": sample.await_ms,
                "max_await_ms": sample.max_await_ms,
                "util_pct": sample.util_pct,
                "max_util_pct": sample.max_util_pct,
                "queue_depth": sample.queue_depth,
                "samples_count": sample.samples_count,
            },
            confidence="MEDIUM",
        )

    for key, value in sorted((extra_evidence or {}).items()):
        if value in (None, "", [], {}):
            continue
        builder.observation(
            kind=f"collector.{key}",
            source=key,
            subject=key,
            value=value,
            confidence="MEDIUM",
            notes=["Supplemental local collector evidence; used to improve review context."],
        )

    if data_mount_obs:
        builder.inference(
            kind="data_mounts_identified",
            statement=f"{len(data_mount_obs)} likely data mount(s) were identified.",
            confidence="HIGH" if "ROOT_ONLY_STORAGE_VIEW" not in fit_reason_codes else "MEDIUM",
            evidence_ids=data_mount_obs,
            requirement_fields=["storage_request_gib"],
        )
    if shared_obs:
        builder.inference(
            kind="shared_namespace_dependency",
            statement="At least one candidate data mount uses a shared or network filesystem.",
            confidence="HIGH",
            evidence_ids=shared_obs,
            requirement_fields=["required_access_mode", "preferred_storage_kind"],
        )
    if latency_obs:
        builder.inference(
            kind="latency_sensitive_review",
            statement="Observed storage latency or utilization raises risk and requires deeper storage testing.",
            confidence="MEDIUM",
            evidence_ids=latency_obs,
            requirement_fields=["required_performance_tier"],
        )
    if process_info.database_processes or process_info.stateful_processes:
        builder.inference(
            kind="block_backed_filesystem_preferred",
            statement="Database-like or stateful service processes make block-backed filesystem storage the default preference unless shared filesystem evidence overrides it.",
            confidence="MEDIUM",
            evidence_ids=[
                obs.id
                for obs in builder.observations
                if obs.kind in {"process.database_like", "process.stateful_service"}
            ],
            requirement_fields=["preferred_storage_kind"],
        )
    if process_info.file_server_processes:
        builder.inference(
            kind="architecture_review_required",
            statement="File-serving process evidence requires human review of the intended shared-storage access pattern.",
            confidence="MEDIUM",
            evidence_ids=[obs.id for obs in builder.observations if obs.kind == "process.file_server"],
            requirement_fields=["shared_namespace_dependency", "writer_topology"],
        )

    return EvidenceGraph(
        observations=builder.observations,
        inferences=builder.inferences,
        missing_facts=sorted(set(missing_data)),
        parse_warnings=parse_warnings,
    )

