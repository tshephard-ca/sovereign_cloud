from pathlib import Path

from gpu_rack_qualifier.evidence_loader import load_evidence
from gpu_rack_qualifier.node_inventory import load_node_inventory
from gpu_rack_qualifier.qualification_policy import load_policy
from gpu_rack_qualifier.rules import qualify_nodes


def test_example_qualification_statuses_are_deterministic():
    root = Path("examples")
    policy = load_policy(root / "qualification_policy.yml")
    inventory = load_node_inventory(root / "node_inventory.yml")
    results = qualify_nodes(load_evidence(root / "evidence", policy), policy, inventory)
    assert [result.features.node_name for result in results] == sorted(result.features.node_name for result in results)
    by_name = {result.features.node_name: result.qualification_status for result in results}
    assert by_name["gpu001"] == "PASS"
    assert by_name["gpu003_weak_link"] == "AVOID_MULTINODE"
    assert by_name["gpu004_sensor_warn"] == "INFERENCE_ONLY"
