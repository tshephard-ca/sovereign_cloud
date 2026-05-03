import csv
import json

from typer.testing import CliRunner

from rag_permission_canary.cli import app
from rag_permission_canary.evidence import CANARY_QUERY_COLUMNS, SAMPLES_COLUMNS


def test_cli_validate_generate_run_report(tmp_path, write_yaml, big_content, big_users, big_permissions, endpoint_payload):
    runner = CliRunner()
    content = write_yaml("content.yml", big_content)
    users = write_yaml("users.yml", big_users)
    perms = write_yaml("permissions.yml", big_permissions)
    endpoint = write_yaml("endpoint.yml", endpoint_payload)
    validate = runner.invoke(app, ["validate", "--content", str(content), "--users", str(users), "--permissions", str(perms), "--endpoint", str(endpoint)])
    assert validate.exit_code == 0, validate.output
    pack = tmp_path / "pack.yml"
    queries = tmp_path / "queries.csv"
    generated = runner.invoke(app, ["generate", "--content", str(content), "--users", str(users), "--permissions", str(perms), "--output-pack", str(pack), "--output-queries", str(queries), "--now", "2026-01-01T00:00:00Z"])
    assert generated.exit_code == 0, generated.output
    with queries.open(encoding="utf-8", newline="") as handle:
        assert next(csv.reader(handle)) == CANARY_QUERY_COLUMNS
    results = tmp_path / "results.json"
    samples = tmp_path / "samples.csv"
    run = runner.invoke(app, ["run", "--pack", str(pack), "--endpoint", str(endpoint), "--output-results", str(results), "--output-samples", str(samples), "--dry-run", "--now", "2026-01-01T00:00:00Z"])
    assert run.exit_code == 0, run.output
    with samples.open(encoding="utf-8", newline="") as handle:
        assert next(csv.reader(handle)) == SAMPLES_COLUMNS
    report = tmp_path / "report.md"
    junit = tmp_path / "junit.xml"
    reported = runner.invoke(app, ["report", "--results", str(results), "--output-report", str(report), "--output-junit", str(junit)])
    assert reported.exit_code == 0, reported.output
    assert report.exists()
    assert junit.exists()


def test_cli_run_fail_on_review_exit_code(tmp_path, write_yaml, big_content, big_users, big_permissions, endpoint_payload):
    runner = CliRunner()
    content = write_yaml("content.yml", big_content)
    users = write_yaml("users.yml", big_users)
    perms = write_yaml("permissions.yml", big_permissions)
    endpoint = write_yaml("endpoint.yml", endpoint_payload)
    pack = tmp_path / "pack.yml"
    queries = tmp_path / "queries.csv"
    runner.invoke(app, ["generate", "--content", str(content), "--users", str(users), "--permissions", str(perms), "--output-pack", str(pack), "--output-queries", str(queries)])
    result = runner.invoke(app, ["run", "--pack", str(pack), "--endpoint", str(endpoint), "--output-results", str(tmp_path / "results.json"), "--output-samples", str(tmp_path / "samples.csv"), "--dry-run", "--fail-on-review"])
    assert result.exit_code == 3


def test_cli_validate_returns_nonzero_for_invalid_inputs(tmp_path, write_yaml, big_content, big_users, endpoint_payload):
    runner = CliRunner()
    content = write_yaml("content.yml", big_content)
    users = write_yaml("users.yml", big_users)
    endpoint = write_yaml("endpoint.yml", endpoint_payload)
    permissions = write_yaml("permissions.yml", {"permission_model": "group_acl", "default_access": "allow"})
    result = runner.invoke(app, ["validate", "--content", str(content), "--users", str(users), "--permissions", str(permissions), "--endpoint", str(endpoint)])
    assert result.exit_code == 1
