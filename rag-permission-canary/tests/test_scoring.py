import httpx

from rag_permission_canary.config import load_config
from rag_permission_canary.endpoint_profile import load_endpoint_profile
from rag_permission_canary.scoring import run_pack
from rag_permission_canary.users import load_users

from conftest import mock_transport


def test_aggregate_pass_when_all_cases_pass(write_yaml, generated_pack, endpoint_payload, big_users, monkeypatch):
    pack, content_path = generated_pack
    endpoint = load_endpoint_profile(write_yaml("endpoint.yml", endpoint_payload))
    users = load_users(write_yaml("users.yml", big_users))
    payload = {"answer": "CANARY_DOC_01", "citations": [{"doc_id": "doc_01", "title": "Doc 01", "snippet": "CANARY_DOC_01"}]}
    results = run_pack(pack=pack.model_copy(update={"test_cases": pack.test_cases[:2]}), endpoint=endpoint, users=users, content_path=content_path, config=load_config(None), transport=mock_transport(payload))
    assert results.aggregate_status in {"PASS", "REVIEW"}
    assert all(item.status == "PASS" for item in results.test_results)


def test_aggregate_fail_when_forbidden_canary_leaks(write_yaml, generated_pack, endpoint_payload, big_users):
    pack, content_path = generated_pack
    forbidden = next(case for case in pack.test_cases if case.expected_result == "FORBIDDEN")
    endpoint = load_endpoint_profile(write_yaml("endpoint.yml", endpoint_payload))
    users = load_users(write_yaml("users.yml", big_users))
    payload = {"answer": forbidden.leakage_checks.forbidden_canary_texts[0], "citations": []}
    results = run_pack(pack=pack.model_copy(update={"test_cases": [forbidden]}), endpoint=endpoint, users=users, content_path=content_path, config=load_config(None), transport=mock_transport(payload))
    assert results.aggregate_status == "FAIL"
    assert results.leakage_summary["forbidden_canary_leaks"] >= 1


def test_aggregate_review_when_allowed_evidence_incomplete(write_yaml, generated_pack, endpoint_payload, big_users):
    pack, content_path = generated_pack
    allowed = next(case for case in pack.test_cases if case.expected_result == "ALLOWED")
    endpoint = load_endpoint_profile(write_yaml("endpoint.yml", endpoint_payload))
    users = load_users(write_yaml("users.yml", big_users))
    results = run_pack(pack=pack.model_copy(update={"test_cases": [allowed]}), endpoint=endpoint, users=users, content_path=content_path, config=load_config(None), transport=mock_transport({"answer": "", "citations": []}))
    assert results.aggregate_status == "REVIEW"


def test_http_auth_failure_fails_test(write_yaml, generated_pack, endpoint_payload, big_users, monkeypatch):
    pack, content_path = generated_pack
    endpoint = load_endpoint_profile(write_yaml("endpoint.yml", endpoint_payload))
    users = load_users(write_yaml("users.yml", big_users))
    results = run_pack(pack=pack.model_copy(update={"test_cases": [pack.test_cases[0]]}), endpoint=endpoint, users=users, content_path=content_path, config=load_config(None), transport=mock_transport({"error": "no"}, 401))
    assert results.test_results[0].status == "FAIL"


def test_timeout_reviews_or_fails_based_on_config(write_yaml, generated_pack, endpoint_payload, big_users):
    def handler(request):
        raise httpx.TimeoutException("timeout")

    pack, content_path = generated_pack
    endpoint = load_endpoint_profile(write_yaml("endpoint.yml", endpoint_payload))
    users = load_users(write_yaml("users.yml", big_users))
    results = run_pack(pack=pack.model_copy(update={"test_cases": [pack.test_cases[0]]}), endpoint=endpoint, users=users, content_path=content_path, config=load_config(None), transport=httpx.MockTransport(handler))
    assert results.test_results[0].status == "REVIEW"


def test_dry_run_and_no_network_do_not_send_requests(write_yaml, generated_pack, endpoint_payload, big_users):
    def handler(request):
        raise AssertionError("network called")

    pack, content_path = generated_pack
    endpoint = load_endpoint_profile(write_yaml("endpoint.yml", endpoint_payload))
    users = load_users(write_yaml("users.yml", big_users))
    dry = run_pack(pack=pack.model_copy(update={"test_cases": [pack.test_cases[0]]}), endpoint=endpoint, users=users, content_path=content_path, config=load_config(None), dry_run=True, transport=httpx.MockTransport(handler))
    blocked = run_pack(pack=pack.model_copy(update={"test_cases": [pack.test_cases[0]]}), endpoint=endpoint, users=users, content_path=content_path, config=load_config(None), no_network=True, transport=httpx.MockTransport(handler))
    assert dry.test_results[0].status == "SKIPPED"
    assert blocked.test_results[0].status == "SKIPPED"


def test_results_json_includes_leakage_summary(tmp_path, write_yaml, generated_pack, endpoint_payload, big_users):
    from rag_permission_canary.scoring import write_results_json
    import json

    pack, content_path = generated_pack
    forbidden = next(case for case in pack.test_cases if case.expected_result == "FORBIDDEN")
    endpoint = load_endpoint_profile(write_yaml("endpoint.yml", endpoint_payload))
    users = load_users(write_yaml("users.yml", big_users))
    payload = {"answer": forbidden.leakage_checks.forbidden_canary_texts[0], "citations": []}
    results = run_pack(pack=pack.model_copy(update={"test_cases": [forbidden]}), endpoint=endpoint, users=users, content_path=content_path, config=load_config(None), transport=mock_transport(payload))
    output = tmp_path / "results.json"
    write_results_json(output, results)
    assert "leakage_summary" in json.loads(output.read_text(encoding="utf-8"))


def test_samples_csv_has_exact_column_order(tmp_path, write_yaml, generated_pack, endpoint_payload, big_users):
    from rag_permission_canary.scoring import write_samples_csv
    from rag_permission_canary.evidence import SAMPLES_COLUMNS
    import csv

    pack, content_path = generated_pack
    endpoint = load_endpoint_profile(write_yaml("endpoint.yml", endpoint_payload))
    users = load_users(write_yaml("users.yml", big_users))
    results = run_pack(pack=pack.model_copy(update={"test_cases": [pack.test_cases[0]]}), endpoint=endpoint, users=users, content_path=content_path, config=load_config(None), dry_run=True)
    output = tmp_path / "samples.csv"
    write_samples_csv(output, results)
    assert next(csv.reader(output.open(encoding="utf-8", newline=""))) == SAMPLES_COLUMNS


def test_no_network_mode_prevents_endpoint_calls_explicit(write_yaml, generated_pack, endpoint_payload, big_users):
    def handler(request):
        raise AssertionError("network called")

    pack, content_path = generated_pack
    endpoint = load_endpoint_profile(write_yaml("endpoint.yml", endpoint_payload))
    users = load_users(write_yaml("users.yml", big_users))
    results = run_pack(pack=pack.model_copy(update={"test_cases": [pack.test_cases[0]]}), endpoint=endpoint, users=users, content_path=content_path, config=load_config(None), no_network=True, transport=httpx.MockTransport(handler))
    assert "NO_NETWORK_MODE" in results.test_results[0].reason_codes
