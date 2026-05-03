"""Local safe/leaky demo execution without a live endpoint."""

from __future__ import annotations

from pathlib import Path
import json

import httpx

from .access_matrix import build_access_matrix, build_boundary_coverage, write_access_matrix_csv, write_boundary_coverage_csv
from .canary_generate import load_pack
from .config import load_config
from .content_set import document_by_id, load_content_set
from .demo_data import generate_demo_fixtures
from .endpoint_profile import load_endpoint_profile
from .fixture_quality import assess_fixture, write_fixture_quality_json, write_fixture_quality_markdown
from .junit import write_junit
from .permissions import load_permissions
from .report import write_markdown_report
from .scoring import run_pack, write_results_json, write_samples_csv
from .users import load_users


def run_demo(
    output_dir: Path,
    mode: str = "safe",
    users_count: int = 4,
    documents_count: int = 20,
    seed: int = 1,
    force: bool = False,
    now: str | None = None,
) -> dict[str, Path]:
    if mode not in {"safe", "leaky"}:
        raise ValueError("mode must be safe or leaky")
    generated = generate_demo_fixtures(output_dir, users_count, documents_count, seed, force=force, now=now)
    run_dir = output_dir / f"run_{mode}"
    run_dir.mkdir(parents=True, exist_ok=True)
    content = load_content_set(generated["content"])
    users = load_users(generated["users"])
    permissions = load_permissions(generated["permissions"])
    endpoint = load_endpoint_profile(generated["endpoint"])
    config = load_config(generated["config"])
    pack = load_pack(generated["pack"])
    docs = document_by_id(content)
    cases = {case.test_case_id: case for case in pack.test_cases}
    transport = httpx.MockTransport(lambda request: _demo_response(request, mode, cases, docs))
    results = run_pack(pack=pack, endpoint=endpoint, users=users, content_path=generated["content"], config=config, transport=transport, now=now)
    results_path = run_dir / "results.json"
    test_results_path = run_dir / "test_results.csv"
    report_path = run_dir / "permission_regression_report.md"
    junit_path = run_dir / "junit.xml"
    access_matrix_path = run_dir / "access_matrix.csv"
    boundary_coverage_path = run_dir / "boundary_coverage.csv"
    quality_json_path = run_dir / "fixture_quality.json"
    quality_md_path = run_dir / "fixture_quality.md"
    write_results_json(results_path, results)
    write_samples_csv(test_results_path, results)
    write_markdown_report(report_path, results)
    write_junit(junit_path, results)
    access_rows = build_access_matrix(content, users, permissions, config, pack, results)
    write_access_matrix_csv(access_matrix_path, access_rows)
    write_boundary_coverage_csv(boundary_coverage_path, build_boundary_coverage(access_rows))
    quality = assess_fixture(content, users, permissions, endpoint, config, pack)
    write_fixture_quality_json(quality_json_path, quality)
    write_fixture_quality_markdown(quality_md_path, quality)
    return {
        **generated,
        "results": results_path,
        "test_results": test_results_path,
        "report": report_path,
        "junit": junit_path,
        "run_access_matrix": access_matrix_path,
        "run_boundary_coverage": boundary_coverage_path,
        "run_fixture_quality_json": quality_json_path,
        "run_fixture_quality_markdown": quality_md_path,
    }


def _demo_response(request: httpx.Request, mode: str, cases: dict, docs: dict) -> httpx.Response:
    payload = json.loads(request.content.decode("utf-8"))
    case = cases[payload["test_case_id"]]
    target = docs[case.target_doc_id]
    if case.expected_result == "FORBIDDEN" and mode == "safe":
        return httpx.Response(200, json={"answer": "No results available for this request.", "citations": [], "metadata": {}, "retrieved_context": ""})
    if case.expected_result == "FORBIDDEN" and mode == "leaky":
        canary_text = target.canaries[0].text if target.canaries else ""
        return httpx.Response(
            200,
            json={
                "answer": f"Leaked restricted evidence from {target.title}: {canary_text}",
                "citations": [{"doc_id": target.doc_id, "title": target.title, "snippet": target.body}],
                "metadata": target.metadata,
                "retrieved_context": target.body,
            },
        )
    canary_text = target.canaries[0].text if target.canaries else ""
    return httpx.Response(
        200,
        json={
            "answer": f"Allowed evidence found in {target.title}: {canary_text}",
            "citations": [{"doc_id": target.doc_id, "title": target.title, "snippet": target.body}],
            "metadata": target.metadata,
            "retrieved_context": target.body,
        },
    )
