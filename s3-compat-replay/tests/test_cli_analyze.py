from __future__ import annotations

import json

from typer.testing import CliRunner

from s3_compat_replay.cli import app

from conftest import make_event, write_records


def test_cli_analyze_writes_outputs(tmp_path):
    cloudtrail = write_records(tmp_path / "events.json", [make_event("GetObject"), make_event("ListObjectsV2", key=None, requestParameters={"bucketName": "source-bucket-example", "prefix": "docs/"})])
    output_profile = tmp_path / "out" / "usage-profile.json"
    output_plan = tmp_path / "out" / "probe-plan.yml"
    output_needs = tmp_path / "out" / "compatibility-needs.csv"
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "--cloudtrail",
            str(cloudtrail),
            "--source-bucket",
            "source-bucket-example",
            "--output-profile",
            str(output_profile),
            "--output-plan",
            str(output_plan),
            "--output-needs",
            str(output_needs),
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(output_profile.read_text(encoding="utf-8"))["processed_event_count"] == 2
    assert output_plan.exists()
    assert output_needs.exists()


def test_strict_analyze_fails_on_no_matching_source_bucket_events(tmp_path):
    cloudtrail = write_records(tmp_path / "events.json", [make_event("GetObject", bucket="other")])
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            "--cloudtrail",
            str(cloudtrail),
            "--source-bucket",
            "source-bucket-example",
            "--output-profile",
            str(tmp_path / "p.json"),
            "--output-plan",
            str(tmp_path / "p.yml"),
            "--output-needs",
            str(tmp_path / "n.csv"),
            "--strict",
        ],
    )
    assert result.exit_code != 0
    assert "no matching source-bucket events" in result.output
