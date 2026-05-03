from pathlib import Path

from gpu_rack_qualifier.features import derive_features
from gpu_rack_qualifier.models import NodeEvidence, QualificationPolicy
from gpu_rack_qualifier.parse_nccl import parse_pairwise_nccl_csv, parse_single_node_nccl
from gpu_rack_qualifier.scoring import compute_peer_median


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_parses_all_reduce_perf_text_output(tmp_path):
    path = _write(
        tmp_path / "nccl.txt",
        "# size count type redop root time algbw busbw wrong\n"
        "8388608 1 float sum -1 0.1 50 100 0\n"
        "67108864 1 float sum -1 0.2 100 200 0\n",
    )
    result = parse_single_node_nccl(path, 67108864)
    assert result.parsed
    assert result.status == "PASS"
    assert result.samples[1].busbw_gbps == 200


def test_parses_all_reduce_perf_csv_output(tmp_path):
    path = _write(tmp_path / "nccl.csv", "size,algbw,busbw,wrong\n67108864,100,200,0\n")
    result = parse_single_node_nccl(path, 67108864)
    assert result.parsed
    assert result.p50_bandwidth_gbps == 200


def test_detects_nonzero_wrong_count(tmp_path):
    path = _write(tmp_path / "nccl.txt", "# size algbw busbw wrong\n67108864 100 200 1\n")
    result = parse_single_node_nccl(path, 67108864)
    assert result.correctness_error
    assert "NCCL_WRONG_COUNT_NONZERO" in result.reason_codes


def test_detects_nccl_timeout_marker(tmp_path):
    path = _write(tmp_path / "nccl.txt", "TIMEOUT waiting for ranks\n")
    result = parse_single_node_nccl(path, 67108864)
    assert result.timeout
    assert result.status == "TIMEOUT"


def test_computes_p50_busbw_for_eligible_message_sizes(tmp_path):
    path = _write(
        tmp_path / "nccl.txt",
        "# size algbw busbw wrong\n"
        "1048576 10 20 0\n"
        "67108864 50 100 0\n"
        "134217728 100 300 0\n"
        "268435456 200 500 0\n",
    )
    result = parse_single_node_nccl(path, 67108864)
    assert result.p50_bandwidth_gbps == 300


def test_ignores_too_small_message_sizes_for_scoring(tmp_path):
    path = _write(tmp_path / "nccl.txt", "# size algbw busbw wrong\n1048576 10 20 0\n67108864 50 100 0\n")
    result = parse_single_node_nccl(path, 67108864)
    assert result.p50_bandwidth_gbps == 100


def test_compares_node_bandwidth_to_peer_median(tmp_path):
    strong = NodeEvidence(node_name="node-a", path=tmp_path, nccl_single=parse_single_node_nccl(_write(tmp_path / "a.txt", "# size algbw busbw wrong\n67108864 1 100 0\n"), 67108864))
    other = NodeEvidence(node_name="node-b", path=tmp_path, nccl_single=parse_single_node_nccl(_write(tmp_path / "b.txt", "# size algbw busbw wrong\n67108864 1 200 0\n"), 67108864))
    assert compute_peer_median([strong, other]) == 150


def test_marks_below_warning_threshold(tmp_path):
    evidence = NodeEvidence(node_name="node-a", path=tmp_path, nccl_single=parse_single_node_nccl(_write(tmp_path / "a.txt", "# size algbw busbw wrong\n67108864 1 70 0\n"), 67108864))
    policy = QualificationPolicy()
    features = derive_features(evidence, policy, peer_median=100)
    assert "NCCL_BELOW_PEER_MEDIAN_WARNING" in features.reason_codes


def test_marks_below_fail_threshold(tmp_path):
    evidence = NodeEvidence(node_name="node-a", path=tmp_path, nccl_single=parse_single_node_nccl(_write(tmp_path / "a.txt", "# size algbw busbw wrong\n67108864 1 40 0\n"), 67108864))
    policy = QualificationPolicy()
    features = derive_features(evidence, policy, peer_median=100)
    assert "NCCL_BELOW_PEER_MEDIAN_FAIL" in features.reason_codes


def test_parses_pairwise_nccl_csv_and_counts_weak_and_timeout(tmp_path):
    path = _write(
        tmp_path / "pairwise.csv",
        "test_id,nodes,gpus_per_node,message_size_bytes,busbw_gbps,algbw_gbps,duration_ms,status,timeout\n"
        "p1,node-a|node-b,4,268435456,100,50,1,PASS,false\n"
        "p2,node-a|node-c,4,268435456,,,1,TIMEOUT,true\n",
    )
    result = parse_pairwise_nccl_csv(path, 67108864, min_pairwise_busbw_gbps=250)
    assert result.parsed
    assert result.weak_peer_count == 2
    assert result.timeout_count == 1
    assert "NCCL_PAIRWISE_TIMEOUT" in result.reason_codes
