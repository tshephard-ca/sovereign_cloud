from gpu_rack_qualifier.models import DerivedNodeFeatures, QualificationResult
from gpu_rack_qualifier.quarantine import quarantine_row


def test_quarantine_row_contains_review_recommendation():
    result = QualificationResult(
        features=DerivedNodeFeatures(node_name="node-a", confidence="HIGH", blockers=["BMC_HEALTH_CRITICAL"], reason_codes=["LABEL_QUARANTINE"]),
        qualification_status="QUARANTINE",
        slurm_features=["rackq_quarantine", "gpu_do_not_schedule"],
        recommended_state="QUARANTINE_REVIEW",
        recommended_partition_hint="do-not-schedule",
    )
    row = quarantine_row(result)
    assert row.recommendation == "QUARANTINE_REVIEW"
    assert row.suggested_slurm_state == "DRAIN"
