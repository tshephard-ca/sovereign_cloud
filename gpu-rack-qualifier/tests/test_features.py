from gpu_rack_qualifier.evidence_loader import load_evidence
from gpu_rack_qualifier.features import derive_features
from gpu_rack_qualifier.models import NodeEvidence, QualificationPolicy
from gpu_rack_qualifier.node_inventory import load_node_inventory
from gpu_rack_qualifier.qualification_policy import load_policy
from gpu_rack_qualifier.rules import qualify_nodes


def test_example_derived_features_include_expected_counts():
    policy = load_policy(__import__("pathlib").Path("examples/qualification_policy.yml"))
    inventory = load_node_inventory(__import__("pathlib").Path("examples/node_inventory.yml"))
    nodes = load_evidence(__import__("pathlib").Path("examples/evidence"), policy)
    results = qualify_nodes(nodes, policy, inventory)
    by_name = {result.features.node_name: result for result in results}
    assert by_name["gpu001"].features.gpu_count == 4
    assert by_name["gpu001"].features.expected_gpu_count == 4
    assert by_name["gpu004_sensor_warn"].features.bmc_warning_count == 1


def test_missing_bmc_snapshot_yields_warning_not_blocker(tmp_path):
    policy = QualificationPolicy()
    policy.evidence.require_bmc_snapshot = False
    features = derive_features(NodeEvidence(node_name="node-a", path=tmp_path), policy)
    assert "BMC_SNAPSHOT_MISSING" in features.warnings
    assert "BMC_SNAPSHOT_MISSING" not in features.blockers
