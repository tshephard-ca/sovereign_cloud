from __future__ import annotations

from statistics import median

from .models import NodeEvidence


def compute_peer_median(nodes: list[NodeEvidence]) -> float | None:
    values = [
        node.nccl_single.p50_bandwidth_gbps
        for node in nodes
        if node.nccl_single.p50_bandwidth_gbps is not None and node.nccl_single.status == "PASS"
    ]
    if len(values) < 2:
        return None
    return float(median(values))


def pct_of_peer(value: float | None, peer_median: float | None) -> float | None:
    if value is None or peer_median in {None, 0}:
        return None
    return round(value / peer_median * 100, 2)


def sorted_unique(values: list[str]) -> list[str]:
    return sorted(set(value for value in values if value))
