from gpu_rack_qualifier.qualification_policy import load_policy


def test_loads_policy(tmp_path):
    path = tmp_path / "policy.yml"
    path.write_text("policy_id: p1\nnccl:\n  peer_median_warning_pct: 80\n", encoding="utf-8")
    policy = load_policy(path)
    assert policy.policy_id == "p1"
    assert policy.nccl.peer_median_warning_pct == 80
