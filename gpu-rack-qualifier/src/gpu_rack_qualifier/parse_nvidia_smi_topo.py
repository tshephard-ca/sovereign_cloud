from __future__ import annotations

import re
from pathlib import Path

from .models import TopologyMatrix


GPU_LABELS = {"X", "N/A", "PIX", "PXB", "PHB", "NODE", "SYS"} | {f"NV{i}" for i in range(1, 13)}


def parse_topology(topo_m_path: Path, p2p_path: Path | None = None) -> TopologyMatrix:
    result = TopologyMatrix(present=topo_m_path.exists(), reason_codes=["TOPO_PRESENT"] if topo_m_path.exists() else ["TOPO_MISSING"])
    if not topo_m_path.exists():
        return result
    try:
        text = topo_m_path.read_text(encoding="utf-8", errors="replace")
        _parse_topo_m_text(text, result)
        if p2p_path and p2p_path.exists():
            _parse_p2p_text(p2p_path.read_text(encoding="utf-8", errors="replace"), result)
        result.parsed = bool(result.gpu_names)
        if not result.parsed:
            result.reason_codes.append("TOPO_PARSE_FAILED")
    except Exception as exc:  # pragma: no cover - defensive parser boundary
        result.warnings.append(str(exc))
        result.reason_codes.append("TOPO_PARSE_FAILED")
    return result


def _parse_topo_m_text(text: str, result: TopologyMatrix) -> None:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    header: list[str] = []
    header_gpu_indices: list[int] = []
    header_nic_indices: list[int] = []
    for line in lines:
        tokens = line.split()
        if not tokens:
            continue
        if not header and any(token.startswith("GPU") for token in tokens):
            header = tokens
            header_gpu_indices = [idx for idx, token in enumerate(header) if token.startswith("GPU")]
            header_nic_indices = [idx for idx, token in enumerate(header) if _looks_like_nic(token)]
            result.gpu_names = [header[idx] for idx in header_gpu_indices]
            result.nic_names = [header[idx] for idx in header_nic_indices]
            continue
        row_name = tokens[0]
        if not row_name.startswith("GPU") or not header:
            continue
        row_gpu_index = result.gpu_names.index(row_name) if row_name in result.gpu_names else None
        for col_index in header_gpu_indices:
            token_index = col_index + 1
            if token_index >= len(tokens):
                continue
            col_name = header[col_index]
            if row_gpu_index is not None and result.gpu_names.index(col_name) <= row_gpu_index:
                continue
            label = _normalize_path_label(tokens[token_index])
            if label in GPU_LABELS and label != "X":
                result.gpu_gpu_path_counts[label] = result.gpu_gpu_path_counts.get(label, 0) + 1
                if label.startswith("NV"):
                    result.nvlink_path_count += 1
                    if "TOPO_NVLINK_PRESENT" not in result.reason_codes:
                        result.reason_codes.append("TOPO_NVLINK_PRESENT")
        for col_index in header_nic_indices:
            token_index = col_index + 1
            if token_index < len(tokens):
                label = _normalize_path_label(tokens[token_index])
                if label in GPU_LABELS and label != "X":
                    result.gpu_nic_path_counts[label] = result.gpu_nic_path_counts.get(label, 0) + 1
        if "CPU" in header:
            cpu_index = header.index("CPU") + 1
            if cpu_index < len(tokens):
                result.cpu_affinity[row_name] = tokens[cpu_index]
        if "NUMA" in header:
            numa_index = header.index("NUMA") + 1
            if numa_index < len(tokens):
                result.numa_affinity[row_name] = tokens[numa_index]


def _parse_p2p_text(text: str, result: TopologyMatrix) -> None:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    header: list[str] = []
    for line in lines:
        tokens = line.split()
        if not tokens:
            continue
        if not header and any(token.startswith("GPU") for token in tokens):
            header = [token for token in tokens if token.startswith("GPU")]
            continue
        if not header or not tokens[0].startswith("GPU"):
            continue
        row_name = tokens[0]
        values = tokens[1 : 1 + len(header)]
        if row_name not in header:
            continue
        row_index = header.index(row_name)
        for col_index, value in enumerate(values):
            if col_index <= row_index:
                continue
            if value.upper() in {"N/A", "NO", "0", "FALSE"}:
                result.p2p_nvlink_missing_count += 1
    if result.p2p_nvlink_missing_count:
        result.reason_codes.append("TOPO_P2P_NVLINK_MISSING")


def apply_topology_policy_counts(result: TopologyMatrix, weak_paths: list[str], review_paths: list[str]) -> TopologyMatrix:
    result.weak_gpu_path_count = sum(count for label, count in result.gpu_gpu_path_counts.items() if label in set(weak_paths))
    result.review_gpu_path_count = sum(count for label, count in result.gpu_gpu_path_counts.items() if label in set(review_paths))
    if result.weak_gpu_path_count and "TOPO_WEAK_GPU_PATH" not in result.reason_codes:
        result.reason_codes.append("TOPO_WEAK_GPU_PATH")
    if result.review_gpu_path_count and "TOPO_REVIEW_GPU_PATH" not in result.reason_codes:
        result.reason_codes.append("TOPO_REVIEW_GPU_PATH")
    return result


def _looks_like_nic(token: str) -> bool:
    upper = token.upper()
    return bool(re.match(r"^(NIC|NET|IB|ETH|ROCE|EN|MLX)", upper))


def _normalize_path_label(value: str) -> str:
    value = value.strip().upper()
    if value.startswith("NV"):
        return value
    return value
