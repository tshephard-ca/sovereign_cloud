import os

from gpu_rack_qualifier.models import DerivedNodeFeatures, QualificationResult
from gpu_rack_qualifier.slurm_render import render_drain_review, render_slurm_fragment


def _result(name="node-a", state="QUARANTINE_REVIEW"):
    return QualificationResult(
        features=DerivedNodeFeatures(node_name=name, blockers=["BMC_HEALTH_CRITICAL"]),
        qualification_status="QUARANTINE",
        slurm_features=["rackq_quarantine", "gpu_do_not_schedule"],
        recommended_state=state,
        recommended_partition_hint="do-not-schedule",
    )


def test_slurm_features_fragment_is_fully_commented(tmp_path):
    path = tmp_path / "features.conf"
    render_slurm_fragment(path, [_result()])
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines
    assert all(line.startswith("#") for line in lines)


def test_drain_review_script_commands_are_commented_and_not_executable(tmp_path):
    path = tmp_path / "drain_review.sh"
    render_drain_review(path, [_result()])
    lines = path.read_text(encoding="utf-8").splitlines()
    command_lines = [line for line in lines if "scontrol update" in line]
    assert command_lines and all(line.startswith("# ") for line in command_lines)
    assert not (path.stat().st_mode & os.X_OK)
