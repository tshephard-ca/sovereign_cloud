from gpu_rack_qualifier.models import DerivedNodeFeatures, QualificationResult
from gpu_rack_qualifier.redact import redact_results, redact_text


def test_redaction_hides_node_names_and_gpu_uuids():
    result = QualificationResult(
        features=DerivedNodeFeatures(node_name="gpu001", source_evidence=["/tmp/gpu001/GPU-abc-123.xml"], reason_codes=["NCCL_SINGLE_NODE_PASS"]),
        qualification_status="PASS",
    )
    redacted = redact_results([result])[0]
    assert redacted.features.node_name == "node_001"
    assert "gpu001" not in redacted.features.source_evidence[0]
    assert "GPU-abc-123" not in redact_text("GPU-abc-123")


def test_redaction_preserves_reason_codes_and_metrics():
    result = QualificationResult(
        features=DerivedNodeFeatures(node_name="gpu001", single_node_busbw_p50_gbps=123.4, reason_codes=["NCCL_SINGLE_NODE_PASS"]),
        qualification_status="PASS",
    )
    redacted = redact_results([result])[0]
    assert redacted.features.reason_codes == ["NCCL_SINGLE_NODE_PASS"]
    assert redacted.features.single_node_busbw_p50_gbps == 123.4
