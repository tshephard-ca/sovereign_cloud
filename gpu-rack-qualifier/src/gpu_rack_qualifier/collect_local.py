from __future__ import annotations

import json
import subprocess
from pathlib import Path


def collect_local(
    node_name: str,
    output_dir: Path,
    nvidia_smi: Path,
    nccl_all_reduce: Path | None,
    run_single_node_nccl: bool,
    timeout_seconds: int,
) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    events: list[str] = []
    if nvidia_smi.exists():
        _run_to_file([str(nvidia_smi), "topo", "-m"], output_dir / "nvidia_smi_topo_m.txt", timeout_seconds, events)
        _run_to_file([str(nvidia_smi), "topo", "-p2p", "n"], output_dir / "nvidia_smi_topo_p2p_n.txt", timeout_seconds, events)
        _run_to_file([str(nvidia_smi), "-q", "-x"], output_dir / "nvidia_smi_query.xml", timeout_seconds, events)
    else:
        events.append("NVIDIA_SMI_BINARY_NOT_FOUND")
    if run_single_node_nccl:
        if nccl_all_reduce and nccl_all_reduce.exists():
            _run_to_file([str(nccl_all_reduce), "-b", "8M", "-e", "512M", "-f", "2"], output_dir / "nccl_single_node_all_reduce.txt", timeout_seconds, events)
        else:
            events.append("NCCL_BINARY_NOT_FOUND")
    metadata = {
        "node_name": node_name,
        "mode": "LOCAL_ONLY",
        "events": events,
        "notes": [
            "No SSH was used.",
            "No Slurm job was submitted.",
            "No BMC collection was attempted.",
            "No network API was called.",
        ],
    }
    (output_dir / "collect_metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return events


def _run_to_file(command: list[str], output_path: Path, timeout_seconds: int, events: list[str]) -> None:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        output_path.write_text("TIMEOUT\n", encoding="utf-8")
        events.append(f"TIMEOUT:{output_path.name}")
        return
    output_path.write_text(completed.stdout + ("\n" + completed.stderr if completed.stderr else ""), encoding="utf-8")
    if completed.returncode != 0:
        events.append(f"NONZERO_EXIT:{output_path.name}:{completed.returncode}")
