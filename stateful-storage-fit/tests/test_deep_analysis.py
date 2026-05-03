from pathlib import Path

from stateful_storage_fit.engine import analyze_paths

from tests.helpers import DF_DATA, FSTAB_DATA, IOSTAT_LOW, MOUNT_DATA, PROFILE, PS_DB


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_check_attaches_deep_analysis_with_evidence_graph_and_constraints(tmp_path):
    bundle = analyze_paths(
        df=_write(tmp_path / "df.txt", DF_DATA),
        mount=_write(tmp_path / "mount.txt", MOUNT_DATA),
        fstab=_write(tmp_path / "fstab.txt", FSTAB_DATA),
        iostat=_write(tmp_path / "iostat.txt", IOSTAT_LOW),
        ps=_write(tmp_path / "ps.txt", PS_DB),
        storage_profile_path=_write(tmp_path / "profile.yml", PROFILE),
    )
    analysis = bundle.result.analysis
    assert analysis["engine_version"] == "storage-inference-v1"
    assert analysis["evidence_graph"]["observations"]
    assert analysis["behavior_fingerprint"]["sync_write_sensitivity"]["value"] == "likely"
    assert analysis["enhanced_requirement"]["hard_requirements"]
    assert any(item["storage_class"] == "standard-rwo" for item in analysis["compatibility"])


def test_missing_iostat_creates_actionable_evidence_question(tmp_path):
    bundle = analyze_paths(
        df=_write(tmp_path / "df.txt", DF_DATA),
        mount=_write(tmp_path / "mount.txt", MOUNT_DATA),
        fstab=_write(tmp_path / "fstab.txt", FSTAB_DATA),
        ps=_write(tmp_path / "ps.txt", PS_DB),
        storage_profile_path=_write(tmp_path / "profile.yml", PROFILE),
    )
    questions = bundle.result.analysis["evidence_questions"]
    assert any(question["id"] == "collect_iostat" for question in questions)

