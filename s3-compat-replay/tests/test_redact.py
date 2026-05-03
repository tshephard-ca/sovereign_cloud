from __future__ import annotations

from s3_compat_replay.redact import Redactor, redact_presigned_url, redact_text


def test_redacts_presigned_url_signatures():
    redacted = redact_presigned_url("https://target.example.invalid/b/k?X-Amz-Signature=secret&X-Amz-Credential=abc&ok=1")
    assert "secret" not in redacted
    assert "X-Amz-Signature=REDACTED" in redacted
    assert "ok=1" in redacted


def test_redacts_sensitive_text_and_bucket_names():
    assert redact_text("account 123456789012 from 192.0.2.1") == "account account_redacted from ip_redacted"
    redactor = Redactor()
    assert redactor.bucket("source-bucket-example") == "bucket_001"
    assert redactor.bucket("source-bucket-example") == "bucket_001"
    assert redactor.bucket("other") == "bucket_002"
