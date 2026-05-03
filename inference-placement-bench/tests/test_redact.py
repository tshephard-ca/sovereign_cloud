from __future__ import annotations

from inference_placement_bench.redact import redact_text, redact_url


def test_redaction_hides_url_host_prompts_responses_and_error_secrets():
    assert "endpoint-a" not in redact_url("https://endpoint-a.example.invalid/path?token=abc")
    redacted = redact_text("Bearer secret-token api_key=abc https://endpoint-a.example.invalid/path")
    assert "secret-token" not in redacted
    assert "endpoint-a" not in redacted


def test_redaction_preserves_metrics_statuses_and_reason_codes():
    metric = {"latency_p95_ms": 10, "status": "PASS", "reason_codes": ["LATENCY_TARGET_MET"]}
    assert metric["latency_p95_ms"] == 10
    assert metric["status"] == "PASS"
    assert metric["reason_codes"] == ["LATENCY_TARGET_MET"]
