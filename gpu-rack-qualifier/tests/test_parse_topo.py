from pathlib import Path

from gpu_rack_qualifier.parse_nvidia_smi_topo import apply_topology_policy_counts, parse_topology


def test_parses_nvidia_smi_topo_matrix_and_counts_paths(tmp_path):
    topo = tmp_path / "topo.txt"
    topo.write_text(
        "        GPU0 GPU1 GPU2\n"
        "GPU0    X    NV4  PHB\n"
        "GPU1    NV4  X    SYS\n"
        "GPU2    PHB  SYS  X\n",
        encoding="utf-8",
    )
    result = parse_topology(topo)
    apply_topology_policy_counts(result, ["PHB", "SYS"], [])
    assert result.parsed
    assert result.nvlink_path_count == 1
    assert result.weak_gpu_path_count == 2


def test_parses_topo_p2p_n_output(tmp_path):
    topo = tmp_path / "topo.txt"
    p2p = tmp_path / "p2p.txt"
    topo.write_text("        GPU0 GPU1\nGPU0    X    NV4\nGPU1    NV4  X\n", encoding="utf-8")
    p2p.write_text("        GPU0 GPU1\nGPU0    X    N/A\nGPU1    N/A  X\n", encoding="utf-8")
    result = parse_topology(topo, p2p)
    assert result.p2p_nvlink_missing_count == 1
    assert "TOPO_P2P_NVLINK_MISSING" in result.reason_codes
