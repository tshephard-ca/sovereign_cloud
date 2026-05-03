from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from .models import BenchmarkPlan, BenchmarkStep, Constraints, EndpointProfiles, PlannedEndpoint, WorkloadProfile
from .redact import redact_endpoint_for_plan
from .validators import endpoint_eligibility
from .workload_profile import load_or_generate_prompts


def iso_now(now: str | None = None) -> str:
    if now:
        return now
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_plan(
    workload: WorkloadProfile,
    endpoints: EndpointProfiles,
    constraints: Constraints,
    config: dict,
    base_dir: str | Path = ".",
    now: str | None = None,
    max_requests: int | None = None,
    warmup_requests: int | None = None,
    concurrency: int | None = None,
    request_timeout_seconds: float | None = None,
    strict: bool = False,
    redact: bool = False,
    dry_run: bool = False,
) -> BenchmarkPlan:
    prompts = load_or_generate_prompts(workload, base_dir=base_dir)
    measured_requests = max_requests if max_requests is not None else workload.benchmark.measured_requests
    measured_requests = min(measured_requests, workload.benchmark.measured_requests)
    warmups = workload.benchmark.warmup_requests if warmup_requests is None else warmup_requests
    planned: list[PlannedEndpoint] = []
    warnings: list[str] = []
    prompt_ids = [prompt.id for prompt in prompts]
    for index, endpoint in enumerate(endpoints.endpoints):
        eligible, codes, endpoint_warnings = endpoint_eligibility(endpoint, workload, constraints, config, strict=strict)
        warnings.extend(endpoint_warnings)
        if dry_run:
            codes.append("DRY_RUN_ONLY")
        display_name = endpoint.display_name
        base_url_redacted = None
        declared_location = endpoint.declared_location
        if redact:
            redacted = redact_endpoint_for_plan(
                endpoint,
                index,
                preserve_location_labels=config.get("preserve_location_labels", False),
            )
            display_name = redacted["display_name"]
            base_url_redacted = redacted["base_url_redacted"]
            declared_location = redacted["declared_location"]
            warnings.append("REDACTION_ENABLED")
        planned.append(
            PlannedEndpoint(
                endpoint_id=endpoint.endpoint_id,
                display_name=display_name,
                base_url_redacted=base_url_redacted,
                eligible=eligible,
                eligibility_reason_codes=codes,
                benchmark=BenchmarkStep(
                    response_mode=endpoint.response_mode,
                    request_count=measured_requests,
                    warmup_count=warmups,
                    prompt_ids=[prompt_ids[i % len(prompt_ids)] for i in range(measured_requests)],
                )
                if eligible
                else None,
                declared_location=declared_location,
            )
        )
    if not any(endpoint.eligible for endpoint in planned):
        warnings.append("NO_ELIGIBLE_ENDPOINTS")
    if any("SYNTHETIC_PROMPTS_USED" in prompt.warnings for prompt in prompts):
        warnings.append("SYNTHETIC_PROMPTS_USED")
    return BenchmarkPlan(
        workload_id=workload.workload_id,
        generated_at=iso_now(now),
        measured_requests=measured_requests,
        warmup_requests=warmups,
        concurrency=concurrency if concurrency is not None else workload.benchmark.concurrency,
        request_timeout_seconds=request_timeout_seconds
        if request_timeout_seconds is not None
        else workload.benchmark.request_timeout_seconds,
        workload=workload,
        constraints=constraints,
        endpoints=planned,
        endpoint_profiles=endpoints.endpoints,
        prompts=prompts,
        warnings=_unique(warnings),
    )


def write_plan(plan: BenchmarkPlan, path: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(plan.model_dump(mode="json"), sort_keys=False), encoding="utf-8")


def load_plan(path: str) -> BenchmarkPlan:
    return BenchmarkPlan.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def _unique(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if value not in seen:
            out.append(value)
            seen.add(value)
    return out
