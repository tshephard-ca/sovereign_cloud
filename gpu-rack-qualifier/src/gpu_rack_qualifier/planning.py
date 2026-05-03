from __future__ import annotations

import csv
from pathlib import Path

import yaml

from .config import ensure_parent
from .node_inventory import load_node_inventory


PAIRWISE_PLAN_COLUMNS = ["test_id", "nodes", "gpus_per_node", "message_size_bytes", "fabric", "notes"]


def generate_pairwise_plan(
    output_csv: Path,
    inventory_path: Path | None = None,
    node_list: str | None = None,
    strategy: str = "pairwise",
    gpus_per_node: int = 8,
    message_size_bytes: int = 268435456,
    max_pairs: int | None = None,
) -> list[dict[str, object]]:
    nodes, metadata = _nodes_from_inputs(inventory_path, node_list)
    pairs = _pairs(nodes, strategy, metadata)
    if max_pairs is not None:
        pairs = pairs[:max_pairs]
    rows = [
        {
            "test_id": f"pair_{index:04d}",
            "nodes": f"{left}|{right}",
            "gpus_per_node": gpus_per_node,
            "message_size_bytes": message_size_bytes,
            "fabric": _relationship(left, right, metadata, strategy),
            "notes": "review-only plan; command execution is operator controlled",
        }
        for index, (left, right) in enumerate(pairs, 1)
    ]
    ensure_parent(output_csv)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAIRWISE_PLAN_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def render_sbatch_template(
    plan_csv: Path,
    output_script: Path,
    all_reduce_path: str,
    gpus_per_node: int,
    time_limit: str = "00:30:00",
    partition: str | None = None,
) -> None:
    ensure_parent(output_script)
    partition_line = f"#SBATCH --partition={partition}" if partition else "# #SBATCH --partition=<review-site-partition>"
    lines = [
        "#!/usr/bin/env bash",
        "# Review-only pairwise NCCL test template.",
        "# This file was generated but not submitted.",
        "# Review paths, partitions, node names, module setup, and output locations before use.",
        "#SBATCH --job-name=rackq-pairwise-nccl",
        f"#SBATCH --time={time_limit}",
        partition_line,
        f"#SBATCH --gpus-per-node={gpus_per_node}",
        "",
        "set -euo pipefail",
        "",
        f'PLAN_CSV="{plan_csv}"',
        f'ALL_REDUCE="{all_reduce_path}"',
        'OUTPUT_CSV="${RACKQ_PAIRWISE_OUTPUT:-rackq_pairwise_results.csv}"',
        "",
        'echo "test_id,nodes,gpus_per_node,message_size_bytes,busbw_gbps,algbw_gbps,duration_ms,status" > "${OUTPUT_CSV}"',
        'tail -n +2 "${PLAN_CSV}" | while IFS=, read -r test_id nodes gpus_per_node message_size_bytes fabric notes; do',
        '  node_a="${nodes%%|*}"',
        '  node_b="${nodes##*|}"',
        '  echo "# Review command for ${test_id}: ${node_a},${node_b}"',
        '  echo "# srun --nodes=2 --nodelist=${node_a},${node_b} ${ALL_REDUCE} -b ${message_size_bytes} -e ${message_size_bytes} -f 2"',
        "done",
        "",
        "# This template intentionally does not call sbatch or submit itself.",
    ]
    output_script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output_script.chmod(output_script.stat().st_mode & ~0o111)


def import_inventory_csv(input_csv: Path, output_yml: Path, cluster_id: str | None = None, rack_id: str | None = None) -> dict[str, object]:
    with input_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    inventory = {
        "cluster_id": cluster_id,
        "rack_id": rack_id,
        "expected": {},
        "nodes": [],
    }
    for row in rows:
        inventory["nodes"].append(
            {
                "name": row["name"],
                "rack": row.get("rack") or rack_id,
                "rack_position": row.get("rack_position") or None,
                "switch_group": row.get("switch_group") or None,
                "fabric_group": row.get("fabric_group") or None,
                "expected_role": _split(row.get("expected_role", "")),
                "expected_gpu_count": _int_or_none(row.get("expected_gpu_count")),
                "expected_nic_count": _int_or_none(row.get("expected_nic_count")),
                "expected_features": _split(row.get("expected_features", "")),
                "maintenance_window": row.get("maintenance_window") or None,
            }
        )
    ensure_parent(output_yml)
    output_yml.write_text(yaml.safe_dump(inventory, sort_keys=False), encoding="utf-8")
    return inventory


def _nodes_from_inputs(inventory_path: Path | None, node_list: str | None) -> tuple[list[str], dict[str, dict[str, str | None]]]:
    if node_list:
        nodes = [node.strip() for node in node_list.split(",") if node.strip()]
        metadata = {node: {} for node in nodes}
    elif inventory_path:
        inventory = load_node_inventory(inventory_path)
        nodes = [node.name for node in inventory.nodes] if inventory else []
        metadata = {
            node.name: {
                "rack": node.rack,
                "switch_group": node.switch_group,
                "fabric_group": node.fabric_group,
            }
            for node in inventory.nodes
        } if inventory else {}
    else:
        nodes = []
        metadata = {}
    if len(nodes) < 2:
        raise ValueError("at least two nodes are required to generate a pairwise plan")
    return sorted(nodes), metadata


def _pairs(nodes: list[str], strategy: str, metadata: dict[str, dict[str, str | None]]) -> list[tuple[str, str]]:
    if strategy == "ring":
        return [(nodes[index], nodes[(index + 1) % len(nodes)]) for index in range(len(nodes))]
    all_pairs = [(left, right) for left_index, left in enumerate(nodes) for right in nodes[left_index + 1 :]]
    if strategy == "pairwise":
        return all_pairs
    if strategy == "same-rack":
        return [(left, right) for left, right in all_pairs if _same(left, right, metadata, "rack")]
    if strategy == "cross-rack":
        return [(left, right) for left, right in all_pairs if _different(left, right, metadata, "rack")]
    if strategy == "same-switch":
        return [(left, right) for left, right in all_pairs if _same(left, right, metadata, "switch_group")]
    if strategy == "cross-switch":
        return [(left, right) for left, right in all_pairs if _different(left, right, metadata, "switch_group")]
    if strategy == "same-fabric":
        return [(left, right) for left, right in all_pairs if _same(left, right, metadata, "fabric_group")]
    if strategy == "cross-fabric":
        return [(left, right) for left, right in all_pairs if _different(left, right, metadata, "fabric_group")]
    raise ValueError("strategy must be pairwise, ring, same-rack, cross-rack, same-switch, cross-switch, same-fabric, or cross-fabric")


def _same(left: str, right: str, metadata: dict[str, dict[str, str | None]], key: str) -> bool:
    left_value = metadata.get(left, {}).get(key)
    right_value = metadata.get(right, {}).get(key)
    return bool(left_value and right_value and left_value == right_value)


def _different(left: str, right: str, metadata: dict[str, dict[str, str | None]], key: str) -> bool:
    left_value = metadata.get(left, {}).get(key)
    right_value = metadata.get(right, {}).get(key)
    return bool(left_value and right_value and left_value != right_value)


def _relationship(left: str, right: str, metadata: dict[str, dict[str, str | None]], strategy: str | None = None) -> str:
    if strategy in {"cross-rack", "cross-switch", "cross-fabric", "same-rack", "same-switch", "same-fabric"}:
        return strategy
    if _same(left, right, metadata, "switch_group"):
        return "same-switch"
    if _same(left, right, metadata, "fabric_group"):
        return "same-fabric"
    if _same(left, right, metadata, "rack"):
        return "same-rack"
    if metadata.get(left) and metadata.get(right):
        return "cross-rack-or-fabric"
    return ""


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.replace("|", ",").split(",") if item.strip()]


def _int_or_none(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
