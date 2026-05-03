from __future__ import annotations

from inference_placement_bench.config import DEFAULT_CONFIG
from inference_placement_bench.plan import build_plan

from conftest import make_constraints, make_endpoint, make_endpoint_profiles, make_workload


def test_marks_endpoint_ineligible_when_workload_type_unsupported():
    plan = build_plan(
        make_workload(),
        make_endpoint_profiles(make_endpoint(workload_types=["embedding"])),
        make_constraints(),
        DEFAULT_CONFIG,
        now="2026-01-01T00:00:00Z",
    )
    assert plan.endpoints[0].eligible is False
    assert "WORKLOAD_TYPE_NOT_SUPPORTED" in plan.endpoints[0].eligibility_reason_codes


def test_marks_endpoint_ineligible_when_streaming_required_but_unsupported():
    plan = build_plan(
        make_workload(streaming_required=True),
        make_endpoint_profiles(make_endpoint(streaming=False, response_mode="non_streaming")),
        make_constraints(),
        DEFAULT_CONFIG,
        now="2026-01-01T00:00:00Z",
    )
    assert "STREAMING_REQUIRED_NOT_SUPPORTED" in plan.endpoints[0].eligibility_reason_codes


def test_marks_endpoint_ineligible_when_context_window_too_small():
    plan = build_plan(
        make_workload(),
        make_endpoint_profiles(make_endpoint(max_context_window_tokens=10)),
        make_constraints(),
        DEFAULT_CONFIG,
        now="2026-01-01T00:00:00Z",
    )
    assert "CONTEXT_WINDOW_TOO_SMALL" in plan.endpoints[0].eligibility_reason_codes


def test_builds_deterministic_benchmark_plan():
    args = (
        make_workload(measured_requests=3, synthetic_prompt_count=2),
        make_endpoint_profiles(make_endpoint("endpoint_a"), make_endpoint("endpoint_b")),
        make_constraints(),
        DEFAULT_CONFIG,
    )
    plan_a = build_plan(*args, now="2026-01-01T00:00:00Z")
    plan_b = build_plan(*args, now="2026-01-01T00:00:00Z")
    assert plan_a.model_dump(mode="json") == plan_b.model_dump(mode="json")


def test_uses_same_prompt_ids_across_eligible_endpoints():
    plan = build_plan(
        make_workload(measured_requests=3, synthetic_prompt_count=2),
        make_endpoint_profiles(make_endpoint("endpoint_a"), make_endpoint("endpoint_b")),
        make_constraints(),
        DEFAULT_CONFIG,
        now="2026-01-01T00:00:00Z",
    )
    assert plan.endpoints[0].benchmark.prompt_ids == plan.endpoints[1].benchmark.prompt_ids


def test_does_not_include_ineligible_endpoints_in_benchmark_steps():
    plan = build_plan(
        make_workload(),
        make_endpoint_profiles(make_endpoint("endpoint_bad", workload_types=["embedding"])),
        make_constraints(),
        DEFAULT_CONFIG,
        now="2026-01-01T00:00:00Z",
    )
    assert plan.endpoints[0].benchmark is None
