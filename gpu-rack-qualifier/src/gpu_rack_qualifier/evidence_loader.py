from __future__ import annotations

from pathlib import Path

from .models import NodeEvidence, QualificationPolicy
from .parse_bmc_snapshot import parse_bmc_snapshot
from .parse_nccl import parse_pairwise_nccl_csv, parse_single_node_nccl
from .parse_nvidia_smi_query import parse_nvidia_smi_query
from .parse_nvidia_smi_topo import apply_topology_policy_counts, parse_topology


SOURCE_FILES = {
    "nccl_single": "nccl_single_node_all_reduce.txt",
    "pairwise_nccl": "nccl_pairwise_all_reduce.csv",
    "topology": "nvidia_smi_topo_m.txt",
    "p2p_topology": "nvidia_smi_topo_p2p_n.txt",
    "nvidia_smi_query": "nvidia_smi_query.xml",
    "bmc_snapshot": "bmc_sensors.redfish.json",
    "collection_metadata": "collection_metadata.json",
}


def load_evidence(evidence_dir: Path, policy: QualificationPolicy) -> list[NodeEvidence]:
    nodes: list[NodeEvidence] = []
    if not evidence_dir.exists():
        return nodes
    for node_path in sorted(path for path in evidence_dir.iterdir() if path.is_dir()):
        source_files = {key: str(node_path / filename) for key, filename in SOURCE_FILES.items() if (node_path / filename).exists()}
        topology = parse_topology(node_path / SOURCE_FILES["topology"], node_path / SOURCE_FILES["p2p_topology"])
        apply_topology_policy_counts(topology, policy.topology.weak_gpu_gpu_paths, policy.topology.review_gpu_gpu_paths)
        nodes.append(
            NodeEvidence(
                node_name=node_path.name,
                path=node_path,
                source_files=source_files,
                nccl_single=parse_single_node_nccl(
                    node_path / SOURCE_FILES["nccl_single"],
                    min_message_size=policy.nccl.min_message_size_bytes_for_scoring,
                    use_metric=policy.nccl.use_metric,
                ),
                pairwise_nccl=parse_pairwise_nccl_csv(
                    node_path / SOURCE_FILES["pairwise_nccl"],
                    min_message_size=policy.nccl.min_message_size_bytes_for_scoring,
                    min_pairwise_busbw_gbps=policy.nccl.min_pairwise_busbw_gbps,
                    local_node=node_path.name,
                ),
                topology=topology,
                nvidia_smi_query=parse_nvidia_smi_query(node_path / SOURCE_FILES["nvidia_smi_query"]),
                bmc_snapshot=parse_bmc_snapshot(node_path / SOURCE_FILES["bmc_snapshot"]),
            )
        )
    return nodes
