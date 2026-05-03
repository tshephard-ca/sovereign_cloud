from __future__ import annotations

from cabinet_burst_envelope.guardrail import generate_sales_ops_guardrail, recommended_questions


def test_guardrail_uses_review_only_language_and_no_approval_language():
    guardrail = generate_sales_ops_guardrail(
        "READY_FOR_REVIEW",
        "HIGH",
        21.5,
        24.0,
        15,
        "ELECTRICAL",
        ["REVIEW_ONLY_OUTPUT"],
        [],
        [],
    )
    text = guardrail.text.lower()
    assert "review-only" in text
    assert "safe to sell" not in text
    assert "guaranteed" not in text
    assert "approved capacity" not in text


def test_low_confidence_uses_discussion_guardrail():
    guardrail = generate_sales_ops_guardrail(
        "REVIEW_REQUIRED",
        "LOW",
        18.0,
        18.0,
        15,
        "DATA_QUALITY",
        ["THERMAL_MODEL_UNUSABLE"],
        [],
        [],
    )
    assert "discussion guardrail" in guardrail.text
    assert "Thermal model is unusable" in guardrail.text


def test_recommended_questions_follow_reason_codes():
    questions = recommended_questions(["BURST_LIMIT_NOT_SUPPLIED", "MISSING_TOP_INLET_SENSOR"], [])
    assert questions[0].startswith("Is short-burst operation allowed")
    assert any("top inlet sensing" in question for question in questions)
