from __future__ import annotations

import random
import shutil
import json
import csv
from pathlib import Path

import yaml

from .config import ensure_parent
from .evidence_bundle import build_evidence_bundle, write_evidence_bundle
from .evidence_loader import load_evidence
from .node_inventory import load_node_inventory
from .qualification_policy import load_policy
from .report import build_summary, write_labels_csv, write_quarantine_csv, write_summary_json
from .action_queue import write_review_queue_csv
from .rules import qualify_nodes
from .slurm_render import render_drain_review, render_slurm_fragment


SCENARIOS = [
    "pass",
    "missing_pairwise_nccl",
    "weak_pairwise",
    "topology_weak_path",
    "topology_review_path",
    "sensor_warning",
    "correctness_error",
    "wrong_count",
    "timeout",
    "missing_gpu",
    "vbios_mismatch",
    "cuda_drift",
    "ecc_mismatch",
    "mig_mismatch",
    "missing_topology",
    "malformed_nccl",
    "malformed_xml",
    "rack_wide_slow_baseline",
    "partial_evidence",
    "bmc_critical",
    "temperature_warning",
    "temperature_critical",
    "sensor_critical",
    "fan_failure",
    "driver_drift",
]


def generate_fixtures(
    output_dir: Path,
    nodes: int = 16,
    gpus_per_node: int = 8,
    scenario: str = "mixed_commissioning",
    seed: int = 1,
    force: bool = False,
) -> dict[str, Path]:
    if output_dir.exists() and any(output_dir.iterdir()):
        if not force:
            raise ValueError(f"{output_dir} is not empty; use --force to replace generated fixtures")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    policy_path = output_dir / "qualification_policy.yml"
    inventory_path = output_dir / "node_inventory.yml"
    assumptions_path = output_dir / "business_assumptions.yml"
    evidence_dir = output_dir / "evidence"
    expected_dir = output_dir / "expected"
    _write_policy(policy_path)
    node_scenarios = _node_scenarios(nodes, scenario)
    _write_inventory(inventory_path, node_scenarios, gpus_per_node)
    _write_business_assumptions(assumptions_path, gpus_per_node)
    _write_scenario_manifest(output_dir / "scenario_manifest.csv", node_scenarios)
    node_names = [f"node{index:03d}" for index in range(1, len(node_scenarios) + 1)]
    for index, node_scenario in enumerate(node_scenarios, 1):
        node_name = node_names[index - 1]
        peer_names = [node_names[(index + offset) % len(node_names)] for offset in range(0, min(3, len(node_names) - 1))]
        _write_node_evidence(evidence_dir / node_name, node_name, peer_names, node_scenario, gpus_per_node, rng, index)
    _write_expected_outputs(policy_path, inventory_path, evidence_dir, expected_dir)
    return {
        "policy": policy_path,
        "inventory": inventory_path,
        "business_assumptions": assumptions_path,
        "scenario_manifest": output_dir / "scenario_manifest.csv",
        "evidence": evidence_dir,
        "expected": expected_dir,
    }


def _write_policy(path: Path) -> None:
    policy = {
        "policy_id": "generated-default",
        "evidence": {
            "require_nccl_single_node": True,
            "require_topo": True,
            "require_nvidia_smi_query": True,
            "require_bmc_snapshot": False,
            "require_pairwise_nccl_for_multinode_label": True,
        },
        "nccl": {
            "use_metric": "busbw_gbps",
            "peer_median_warning_pct": 75,
            "peer_median_fail_pct": 50,
            "min_single_node_busbw_gbps": None,
            "min_pairwise_busbw_gbps": 250,
            "timeout_is_quarantine": True,
            "correctness_error_is_quarantine": True,
            "wrong_count_is_quarantine": True,
            "min_message_size_bytes_for_scoring": 67108864,
        },
        "topology": {
            "require_nvlink_for_multinode_training": False,
            "weak_gpu_gpu_paths": ["SYS", "PHB"],
            "review_gpu_gpu_paths": ["PXB"],
            "weak_if_any_gpu_pair_weak": True,
            "p2p_nvlink_expected": False,
        },
        "firmware": {
            "require_driver_consistency_across_rack": True,
            "require_vbios_consistency_within_node": True,
            "driver_mismatch_action": "REVIEW",
            "vbios_mismatch_action": "DRAIN_REVIEW",
            "cuda_mismatch_action": "REVIEW",
        },
        "sensors": {
            "health_warning_action": "REVIEW",
            "health_critical_action": "QUARANTINE",
            "fan_failure_action": "QUARANTINE",
            "temp_warning_celsius": 80,
            "temp_critical_celsius": 90,
            "power_warning_action": "REVIEW",
            "power_critical_action": "QUARANTINE",
        },
    }
    path.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")


def _write_inventory(path: Path, scenarios: list[str], gpus_per_node: int) -> None:
    inventory = {
        "cluster_id": "generated-cluster",
        "rack_id": "rack-generated-001",
        "expected": {
            "gpu_count": gpus_per_node,
            "gpu_product_name_regex": ".*",
            "driver_version": ">=550.0",
            "cuda_version": ">=12.0",
            "vbios_consistent_within_node": True,
            "mig_mode": "disabled",
            "ecc_mode": "enabled",
        },
        "nodes": [
            {
                "name": f"node{index:03d}",
                "rack": "rack-generated-001",
                "rack_position": f"u{index:02d}",
                "switch_group": f"switch-{((index - 1) // 8) + 1:02d}",
                "fabric_group": f"fabric-{((index - 1) // 16) + 1:02d}",
                "expected_role": ["training", "inference"],
                "expected_gpu_count": gpus_per_node,
                "expected_nic_count": 2,
                "expected_features": ["gpu", "training"],
                "maintenance_window": None,
            }
            for index, _ in enumerate(scenarios, 1)
        ],
    }
    path.write_text(yaml.safe_dump(inventory, sort_keys=False), encoding="utf-8")


def _write_business_assumptions(path: Path, gpus_per_node: int) -> None:
    assumptions = {
        "gpus_per_node": gpus_per_node,
        "hours_at_risk": 24,
        "accelerator_hour_value": 3.5,
        "release_goal": "multinode_training",
    }
    path.write_text(yaml.safe_dump(assumptions, sort_keys=False), encoding="utf-8")


def _write_scenario_manifest(path: Path, scenarios: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "node_name",
                "scenario",
                "expected_signal",
                "expected_operator_concern",
                "expected_business_impact",
            ],
        )
        writer.writeheader()
        for index, scenario in enumerate(scenarios, 1):
            writer.writerow(
                {
                    "node_name": f"node{index:03d}",
                    "scenario": scenario,
                    "expected_signal": _scenario_signal(scenario),
                    "expected_operator_concern": _scenario_operator_concern(scenario),
                    "expected_business_impact": _scenario_business_impact(scenario),
                }
            )


def _node_scenarios(nodes: int, scenario: str) -> list[str]:
    if scenario == "mixed_commissioning":
        if nodes >= len(SCENARIOS):
            return [SCENARIOS[index % len(SCENARIOS)] for index in range(nodes)]
        return SCENARIOS[:nodes]
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario}")
    return [scenario for _ in range(nodes)]


def _scenario_signal(scenario: str) -> str:
    return {
        "pass": "complete qualification evidence",
        "missing_pairwise_nccl": "missing multi-node communication evidence",
        "weak_pairwise": "weak pairwise communication",
        "topology_weak_path": "weak GPU topology paths",
        "topology_review_path": "review-class GPU topology paths",
        "sensor_warning": "BMC and temperature warning",
        "correctness_error": "NCCL correctness marker",
        "wrong_count": "nonzero NCCL wrong count",
        "timeout": "NCCL timeout",
        "missing_gpu": "actual GPU count below expected",
        "vbios_mismatch": "within-node VBIOS mismatch",
        "cuda_drift": "CUDA version mismatch",
        "ecc_mismatch": "ECC mode mismatch",
        "mig_mismatch": "MIG mode mismatch",
        "missing_topology": "missing topology evidence",
        "malformed_nccl": "unparsed NCCL evidence",
        "malformed_xml": "unparsed hardware identity XML",
        "rack_wide_slow_baseline": "slow rack-wide bandwidth baseline",
        "partial_evidence": "missing pairwise evidence",
        "bmc_critical": "critical BMC health",
        "temperature_warning": "temperature warning threshold crossed",
        "temperature_critical": "temperature critical threshold crossed",
        "sensor_critical": "critical sensor and temperature evidence",
        "fan_failure": "fan failure evidence",
        "driver_drift": "driver version mismatch",
    }.get(scenario, "mixed qualification evidence")


def _scenario_operator_concern(scenario: str) -> str:
    if scenario in {"correctness_error", "wrong_count", "timeout"}:
        return "keep node out of normal scheduling until communication correctness is reviewed"
    if scenario in {"bmc_critical", "temperature_critical", "sensor_critical", "fan_failure", "sensor_warning", "temperature_warning"}:
        return "review hardware or facilities state before scheduling"
    if scenario in {"weak_pairwise", "topology_weak_path", "topology_review_path"}:
        return "avoid multi-node training until fabric or topology risk is reviewed"
    if scenario in {"missing_pairwise_nccl", "partial_evidence", "missing_topology", "malformed_nccl", "malformed_xml"}:
        return "collect or repair evidence before broad release"
    if scenario in {"vbios_mismatch", "cuda_drift", "driver_drift", "ecc_mismatch", "mig_mismatch"}:
        return "review firmware or software consistency before broad release"
    if scenario == "missing_gpu":
        return "confirm whether the node is intentionally under-populated or missing hardware"
    return "candidate for normal release from supplied evidence"


def _scenario_business_impact(scenario: str) -> str:
    if scenario == "pass":
        return "candidate capacity for multi-node training release"
    if scenario in {"weak_pairwise", "topology_weak_path", "topology_review_path"}:
        return "protects distributed jobs from weak-link placement"
    if scenario in {"correctness_error", "wrong_count", "timeout"}:
        return "reduces risk of failed or invalid training runs"
    if scenario in {"bmc_critical", "temperature_critical", "sensor_critical", "fan_failure", "sensor_warning", "temperature_warning"}:
        return "reduces thermal or hardware incident risk before user jobs run"
    if scenario in {"missing_pairwise_nccl", "partial_evidence", "missing_topology", "malformed_nccl", "malformed_xml"}:
        return "prevents false confidence from incomplete qualification evidence"
    if scenario in {"vbios_mismatch", "cuda_drift", "driver_drift", "ecc_mismatch", "mig_mismatch"}:
        return "reduces support ambiguity from configuration drift"
    if scenario == "missing_gpu":
        return "prevents scheduling jobs onto under-capacity nodes"
    return "keeps workload placement aligned with evidence quality"


def _write_node_evidence(node_dir: Path, node_name: str, peer_names: list[str], scenario: str, gpus_per_node: int, rng: random.Random, node_index: int) -> None:
    node_dir.mkdir(parents=True, exist_ok=True)
    if scenario not in {"partial_evidence", "missing_pairwise_nccl"}:
        _write_pairwise(node_dir / "nccl_pairwise_all_reduce.csv", node_name, peer_names, scenario, gpus_per_node, node_index)
    _write_nccl(node_dir / "nccl_single_node_all_reduce.txt", scenario, rng)
    if scenario != "missing_topology":
        _write_topology(
            node_dir / "nvidia_smi_topo_m.txt",
            gpus_per_node,
            weak=scenario in {"weak_pairwise", "topology_weak_path"},
            review=scenario == "topology_review_path",
        )
        _write_p2p(node_dir / "nvidia_smi_topo_p2p_n.txt", gpus_per_node, missing=scenario in {"weak_pairwise", "topology_weak_path"})
    gpu_count = gpus_per_node - 1 if scenario == "missing_gpu" else gpus_per_node
    _write_nvidia_xml(node_dir / "nvidia_smi_query.xml", node_name, scenario, gpu_count)
    _write_bmc(node_dir / "bmc_sensors.redfish.json", scenario)
    _write_collection_metadata(node_dir / "collection_metadata.json", node_name, scenario, node_index)


def _write_nccl(path: Path, scenario: str, rng: random.Random) -> None:
    if scenario == "malformed_nccl":
        path.write_text("this is not parseable NCCL tabular output\n", encoding="utf-8")
        return
    if scenario == "timeout":
        path.write_text("TIMEOUT waiting for NCCL all-reduce completion\n", encoding="utf-8")
        return
    wrong = 1 if scenario == "wrong_count" else 0
    base = 390
    if scenario in {"weak_pairwise", "topology_weak_path"}:
        base = 315
    if scenario == "rack_wide_slow_baseline":
        base = 180
    rows = ["# size count type redop root time algbw busbw wrong"]
    for size in [8388608, 67108864, 134217728, 268435456]:
        busbw = base + rng.randint(-8, 8)
        rows.append(f"{size} 1 float sum -1 1.0 {busbw / 2:.1f} {busbw:.1f} {wrong if size == 268435456 else 0}")
    if scenario == "correctness_error":
        rows.append("FAILED correctness mismatch")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_pairwise(path: Path, node_name: str, peer_names: list[str], scenario: str, gpus_per_node: int, node_index: int) -> None:
    header = (
        "test_id,nodes,gpus_per_node,message_size_bytes,busbw_gbps,algbw_gbps,duration_ms,status,"
        "rank_count,mpi_ranks,fabric,job_id,started_at,finished_at,stderr_excerpt,timeout,wrong_count"
    )
    rows = [header]
    for peer_index, peer_name in enumerate(peer_names, 1):
        test_id = f"p{node_index:03d}_{peer_index:02d}"
        fabric = "same-switch" if peer_index == 1 else "same-fabric" if peer_index == 2 else "cross-fabric"
        started = f"2026-01-01T00:{node_index % 60:02d}:{peer_index:02d}Z"
        finished = f"2026-01-01T00:{node_index % 60:02d}:{peer_index + 10:02d}Z"
        if scenario == "timeout" and peer_index == 1:
            rows.append(f'{test_id},{node_name}|{peer_name},{gpus_per_node},268435456,,,300,TIMEOUT,{gpus_per_node * 2},{gpus_per_node * 2},{fabric},job-{test_id},{started},{finished},"timeout waiting for ranks",true,0')
            continue
        busbw = 390
        if scenario == "weak_pairwise":
            busbw = 120 if peer_index <= 2 else 260
        elif scenario == "rack_wide_slow_baseline":
            busbw = 180
        elif fabric == "cross-fabric":
            busbw = 340
        rows.append(f"{test_id},{node_name}|{peer_name},{gpus_per_node},268435456,{busbw},{busbw / 2},60,PASS,{gpus_per_node * 2},{gpus_per_node * 2},{fabric},job-{test_id},{started},{finished},,false,0")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_topology(path: Path, gpus_per_node: int, weak: bool, review: bool = False) -> None:
    header = "        " + " ".join(f"GPU{i}" for i in range(gpus_per_node)) + " NIC0 NIC1 CPU NUMA"
    rows = [header]
    for row in range(gpus_per_node):
        values = []
        for col in range(gpus_per_node):
            if row == col:
                values.append("X")
            elif weak and abs(row - col) > 1:
                values.append("PHB")
            elif review and abs(row - col) > 1:
                values.append("PXB")
            else:
                values.append("NV4")
        rows.append(f"GPU{row}    " + " ".join(values) + " PIX PXB 0-31 0")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_p2p(path: Path, gpus_per_node: int, missing: bool) -> None:
    rows = ["        " + " ".join(f"GPU{i}" for i in range(gpus_per_node))]
    for row in range(gpus_per_node):
        values = ["X" if row == col else "N/A" if missing and abs(row - col) > 1 else "OK" for col in range(gpus_per_node)]
        rows.append(f"GPU{row}    " + " ".join(values))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _write_nvidia_xml(path: Path, node_name: str, scenario: str, gpu_count: int) -> None:
    if scenario == "malformed_xml":
        path.write_text("<nvidia_smi_log><gpu><uuid>GPU-broken</uuid>\n", encoding="utf-8")
        return
    driver = "549.9" if scenario == "driver_drift" else "550.1"
    cuda = "11.8" if scenario == "cuda_drift" else "12.2"
    gpus = []
    for index in range(gpu_count):
        vbios = "90.02" if scenario == "vbios_mismatch" and index == gpu_count - 1 else "90.01"
        ecc = "Disabled" if scenario == "ecc_mismatch" and index == gpu_count - 1 else "Enabled"
        mig = "Enabled" if scenario == "mig_mismatch" and index == gpu_count - 1 else "Disabled"
        gpus.append(
            f"<gpu><product_name>Generic GPU Accelerator</product_name><uuid>GPU-{node_name}-{index}</uuid><vbios_version>{vbios}</vbios_version>"
            f"<serial>SERIAL-{node_name}-{index}</serial><pci><pci_bus_id>0000:{index + 16:02x}:00.0</pci_bus_id></pci>"
            f"<ecc_mode><current_ecc>{ecc}</current_ecc></ecc_mode><mig_mode><current_mig>{mig}</current_mig></mig_mode>"
            "<temperature><gpu_temp>58 C</gpu_temp></temperature>"
            "<power_readings><power_draw>310 W</power_draw><power_limit>450 W</power_limit></power_readings>"
            "<clocks_throttle_reasons><hw_slowdown>Not Active</hw_slowdown><sw_power_cap>Not Active</sw_power_cap></clocks_throttle_reasons>"
            "<retired_pages><single_bit_retirement><retired_count>0</retired_count></single_bit_retirement><double_bit_retirement><retired_count>0</retired_count></double_bit_retirement></retired_pages>"
            "<persistence_mode>Enabled</persistence_mode></gpu>"
        )
    path.write_text(f"<nvidia_smi_log><driver_version>{driver}</driver_version><cuda_version>{cuda}</cuda_version>{''.join(gpus)}</nvidia_smi_log>\n", encoding="utf-8")


def _write_bmc(path: Path, scenario: str) -> None:
    health = "OK"
    temp = 25
    fan = 9000
    if scenario == "sensor_warning":
        health = "Warning"
        temp = 84
    elif scenario == "temperature_warning":
        temp = 84
    elif scenario == "temperature_critical":
        temp = 95
    elif scenario == "bmc_critical":
        health = "Critical"
    elif scenario == "sensor_critical":
        health = "Critical"
        temp = 95
    elif scenario == "fan_failure":
        health = "Critical"
        fan = 0
    content = {
        "Sensors": [
            {"Name": "Outlet Temp", "SensorType": "Temperature", "Reading": temp, "ReadingUnits": "C", "Status": {"State": "Enabled", "Health": health if scenario != "fan_failure" else "OK"}},
            {"Name": "Fan 1", "SensorType": "Fan", "Reading": fan, "ReadingUnits": "RPM", "Status": {"State": "Enabled", "Health": health if scenario == "fan_failure" else "OK"}},
            {"Name": "Fan 2", "SensorType": "Fan", "Reading": 9100, "ReadingUnits": "RPM", "Status": {"State": "Enabled", "Health": "OK"}},
            {"Name": "GPU Board Power", "SensorType": "Power", "Reading": 2450, "ReadingUnits": "W", "UpperThresholdNonCritical": 3000, "UpperThresholdCritical": 3400, "Status": {"State": "Enabled", "Health": "OK"}},
            {"Name": "Power Supply Redundancy", "SensorType": "Power", "Reading": 1, "ReadingUnits": "count", "Status": {"State": "Enabled", "Health": "OK"}},
            {"Name": "12V Rail", "SensorType": "Voltage", "Reading": 12.1, "ReadingUnits": "V", "LowerThresholdNonCritical": 11.4, "LowerThresholdCritical": 10.8, "Status": {"State": "Enabled", "Health": "OK"}},
            {"Name": "GPU Current", "SensorType": "Current", "Reading": 185, "ReadingUnits": "A", "Status": {"State": "Enabled", "Health": "OK"}},
        ]
    }
    path.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_collection_metadata(path: Path, node_name: str, scenario: str, node_index: int) -> None:
    metadata = {
        "schema_version": "rackq.collection_metadata.v1",
        "node_name": node_name,
        "scenario": scenario,
        "collected_at": f"2026-01-01T01:{node_index % 60:02d}:00Z",
        "collector_mode": "GENERATED_FIXTURE",
        "local_only": True,
        "commands": [
            {"name": "nvidia-smi topo -m", "exit_code": 0 if scenario != "missing_topology" else None},
            {"name": "nvidia-smi topo -p2p n", "exit_code": 0 if scenario != "missing_topology" else None},
            {"name": "nvidia-smi -q -x", "exit_code": 0 if scenario != "malformed_xml" else 1},
            {"name": "all_reduce_perf", "exit_code": 0 if scenario not in {"timeout", "correctness_error", "wrong_count", "malformed_nccl"} else 1},
        ],
        "repeat_count": 3,
        "notes": ["synthetic evidence for offline workflow validation"],
    }
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_expected_outputs(policy_path: Path, inventory_path: Path, evidence_dir: Path, expected_dir: Path) -> None:
    expected_dir.mkdir(parents=True, exist_ok=True)
    policy = load_policy(policy_path)
    inventory = load_node_inventory(inventory_path)
    nodes = load_evidence(evidence_dir, policy)
    results = qualify_nodes(nodes, policy, inventory)
    labels = expected_dir / "slurm_node_labels.csv"
    quarantine = expected_dir / "quarantine.csv"
    review_queue = expected_dir / "review_queue.csv"
    slurm = expected_dir / "slurm_features.conf.snippet"
    drain = expected_dir / "drain_review.sh"
    summary_path = expected_dir / "summary.json"
    bundle_path = expected_dir / "evidence_bundle.json"
    outputs = {
        "labels_csv": str(labels),
        "quarantine_csv": str(quarantine),
        "review_queue_csv": str(review_queue),
        "slurm_fragment": str(slurm),
        "drain_review": str(drain),
        "evidence_bundle": str(bundle_path),
    }
    write_labels_csv(labels, results)
    write_quarantine_csv(quarantine, results)
    write_review_queue_csv(review_queue, results)
    render_slurm_fragment(slurm, results)
    render_drain_review(drain, results)
    summary = build_summary(nodes, results, inventory, policy.policy_id, outputs)
    summary.generated_at = "2000-01-01T00:00:00Z"
    write_summary_json(summary_path, summary)
    bundle = build_evidence_bundle(evidence_dir, policy, inventory, nodes, results, outputs, policy_path, inventory_path)
    bundle["generated_at"] = "2000-01-01T00:00:00Z"
    write_evidence_bundle(bundle_path, bundle)
