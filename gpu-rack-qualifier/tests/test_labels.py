from gpu_rack_qualifier.labels import generate_labels
from gpu_rack_qualifier.models import DerivedNodeFeatures, QualificationPolicy


def test_pass_node_receives_training_and_inference_labels():
    labels = generate_labels("PASS", DerivedNodeFeatures(node_name="node-a"), QualificationPolicy())
    assert "gpu_training_multinode_ok" in labels
    assert "gpu_training_single_node_ok" in labels
    assert "gpu_inference_ok" in labels


def test_avoid_multinode_node_receives_avoid_label():
    features = DerivedNodeFeatures(node_name="node-a", weak_topology_path_count=1)
    labels = generate_labels("AVOID_MULTINODE", features, QualificationPolicy())
    assert "gpu_avoid_multinode" in labels
    assert "gpu_link_weak" in labels


def test_inference_only_node_does_not_receive_training_labels():
    labels = generate_labels("INFERENCE_ONLY", DerivedNodeFeatures(node_name="node-a"), QualificationPolicy())
    assert "gpu_inference_ok" in labels
    assert "gpu_training_single_node_ok" not in labels
    assert "gpu_training_multinode_ok" not in labels


def test_quarantine_node_receives_do_not_schedule_only():
    features = DerivedNodeFeatures(node_name="node-a", bmc_critical_count=1, blockers=["BMC_HEALTH_CRITICAL"])
    labels = generate_labels("QUARANTINE", features, QualificationPolicy())
    assert labels == ["rackq_quarantine", "gpu_do_not_schedule"]


def test_missing_pairwise_prevents_multinode_label_when_policy_requires_it():
    features = DerivedNodeFeatures(node_name="node-a", gpu_count=4, single_node_nccl_status="PASS", pairwise_nccl_status="MISSING", warnings=["NCCL_PAIRWISE_MISSING"])
    labels = generate_labels("REVIEW", features, QualificationPolicy())
    assert "gpu_training_multinode_ok" not in labels
