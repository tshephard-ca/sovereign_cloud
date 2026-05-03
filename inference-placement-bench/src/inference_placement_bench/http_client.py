from __future__ import annotations

import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from .economics import compute_economics
from .metrics import aggregate_samples, percentile
from .models import BenchmarkPlan, BenchmarkResults, BenchmarkSample, EndpointProfile, EndpointResult, PromptRecord
from .payload_template import render_template
from .redact import redact_text
from .response_extract import extract_json_path
from .scoring import evaluate_benchmark_status
from .simulator import simulator_transport_for_plan
from .sse_parser import parse_sse_lines
from .token_estimate import input_tokens_from_prompt, output_tokens_from_text


def run_benchmark_plan(
    plan: BenchmarkPlan,
    config: dict[str, Any],
    *,
    dry_run: bool = False,
    no_network: bool = False,
    strict: bool = False,
    redact: bool = False,
    transport: httpx.BaseTransport | None = None,
    now: str | None = None,
) -> BenchmarkResults:
    started = _iso_now(now)
    all_samples: list[BenchmarkSample] = []
    endpoint_results: list[EndpointResult] = []
    endpoint_by_id = {endpoint.endpoint_id: endpoint for endpoint in plan.endpoint_profiles}
    prompt_by_id = {prompt.id: prompt for prompt in plan.prompts}
    warnings = list(plan.warnings)
    effective_transport = transport or simulator_transport_for_plan(plan)
    if dry_run:
        warnings.append("DRY_RUN_ONLY")
    if no_network and effective_transport is None and not dry_run:
        raise RuntimeError("NETWORK_DISABLED_BY_NO_NETWORK")

    for planned in plan.endpoints:
        endpoint = endpoint_by_id[planned.endpoint_id]
        if not planned.eligible or planned.benchmark is None:
            metrics = aggregate_samples([], measured_wall_seconds=0)
            metrics.eligibility_status = "INELIGIBLE"
            metrics.benchmark_status = "INELIGIBLE"
            metrics.reason_codes = planned.eligibility_reason_codes + ["BENCHMARK_NOT_RUN"]
            endpoint_results.append(
                EndpointResult(
                    endpoint_id=planned.endpoint_id,
                    eligibility_status="INELIGIBLE",
                    benchmark_status="INELIGIBLE",
                    declared_location=planned.declared_location,
                    metrics=metrics,
                    economics={},
                    reason_codes=metrics.reason_codes,
                    warnings=[],
                )
            )
            continue

        if dry_run:
            metrics = aggregate_samples([], measured_wall_seconds=0)
            metrics.eligibility_status = "ELIGIBLE"
            metrics.benchmark_status = "ELIGIBLE_NOT_RUN"
            metrics.reason_codes = planned.eligibility_reason_codes + ["DRY_RUN_ONLY", "BENCHMARK_NOT_RUN", "REVIEW_ONLY_OUTPUT"]
            endpoint_results.append(
                EndpointResult(
                    endpoint_id=planned.endpoint_id,
                    eligibility_status="ELIGIBLE",
                    benchmark_status="ELIGIBLE_NOT_RUN",
                    declared_location=planned.declared_location,
                    metrics=metrics,
                    economics={},
                    reason_codes=metrics.reason_codes,
                    warnings=[],
                )
            )
            continue

        endpoint_samples: list[BenchmarkSample] = []
        wall_start = time.perf_counter()
        with httpx.Client(
            timeout=plan.request_timeout_seconds,
            transport=effective_transport,
            headers={"User-Agent": config.get("http", {}).get("user_agent", "inference-placement-bench/0.1")},
        ) as client:
            warmup_ids = [planned.benchmark.prompt_ids[i % len(planned.benchmark.prompt_ids)] for i in range(planned.benchmark.warmup_count)]
            for source_row, prompt_id in enumerate(warmup_ids, start=1):
                endpoint_samples.append(
                    execute_request(
                        client,
                        endpoint,
                        plan,
                        prompt_by_id[prompt_id],
                        measured=False,
                        source_row=source_row,
                        config=config,
                        redact=redact,
                    )
                )
            measured_start = time.perf_counter()
            endpoint_samples.extend(
                _execute_measured_requests(
                    client,
                    endpoint,
                    plan,
                    [prompt_by_id[prompt_id] for prompt_id in planned.benchmark.prompt_ids],
                    config=config,
                    redact=redact,
                )
            )
            measured_seconds = max(0.000001, time.perf_counter() - measured_start)
        _ = wall_start
        all_samples.extend(endpoint_samples)
        measured_samples = [sample for sample in endpoint_samples if sample.measured]
        metrics = aggregate_samples(
            endpoint_samples,
            measured_wall_seconds=measured_seconds,
            include_failures_in_latency=config.get("include_failures_in_latency", False),
        )
        token_sources = [sample.token_count_source or "UNKNOWN" for sample in measured_samples if sample.status == "SUCCESS"]
        economics, econ_reasons, econ_warnings = compute_economics(
            endpoint.unit_economics,
            metrics,
            metrics.success_count,
            token_sources,
        )
        status, reason_codes, endpoint_warnings = evaluate_benchmark_status(
            metrics,
            plan.constraints,
            config,
            eligibility_ok=True,
            existing_reason_codes=planned.eligibility_reason_codes + econ_reasons,
            existing_warnings=econ_warnings + [warning for sample in endpoint_samples for warning in sample.warnings],
        )
        if strict and status == "FAIL":
            raise RuntimeError(f"benchmark failed for {endpoint.endpoint_id}")
        metrics.eligibility_status = "ELIGIBLE"
        metrics.benchmark_status = status
        metrics.reason_codes = reason_codes
        metrics.warnings = endpoint_warnings
        metrics.estimated_cost_per_1k_requests = economics.get("estimated_cost_per_1k_requests")
        metrics.estimated_cost_per_1m_input_tokens = economics.get("estimated_cost_per_1m_input_tokens")
        metrics.estimated_cost_per_1m_output_tokens = economics.get("estimated_cost_per_1m_output_tokens")
        metrics.estimated_cost_for_benchmark_run = economics.get("estimated_cost_for_benchmark_run")
        endpoint_results.append(
            EndpointResult(
                endpoint_id=endpoint.endpoint_id,
                eligibility_status="ELIGIBLE",
                benchmark_status=status,
                declared_location=planned.declared_location,
                metrics=metrics,
                economics=economics,
                reason_codes=reason_codes,
                warnings=endpoint_warnings,
            )
        )
    finished = _iso_now(now)
    return BenchmarkResults(
        run_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{plan.workload_id}:{started}:{len(all_samples)}")),
        workload_id=plan.workload_id,
        started_at=started,
        finished_at=finished,
        mode="DRY_RUN" if dry_run else "MEASURED_HTTP",
        config={
            "warmup_requests": plan.warmup_requests,
            "measured_requests": plan.measured_requests,
            "concurrency": plan.concurrency,
            "request_timeout_seconds": plan.request_timeout_seconds,
        },
        endpoints=endpoint_results,
        samples=all_samples,
        warnings=_unique(warnings),
    )


def _execute_measured_requests(
    client: httpx.Client,
    endpoint: EndpointProfile,
    plan: BenchmarkPlan,
    prompts: list[PromptRecord],
    *,
    config: dict[str, Any],
    redact: bool,
) -> list[BenchmarkSample]:
    if plan.concurrency <= 1:
        return [
            execute_request(
                client,
                endpoint,
                plan,
                prompt,
                measured=True,
                source_row=source_row,
                config=config,
                redact=redact,
            )
            for source_row, prompt in enumerate(prompts, start=1)
        ]
    samples: list[BenchmarkSample] = []
    with ThreadPoolExecutor(max_workers=plan.concurrency) as executor:
        futures = [
            executor.submit(
                execute_request,
                client,
                endpoint,
                plan,
                prompt,
                measured=True,
                source_row=source_row,
                config=config,
                redact=redact,
            )
            for source_row, prompt in enumerate(prompts, start=1)
        ]
        for future in as_completed(futures):
            samples.append(future.result())
    return sorted(samples, key=lambda sample: sample.source_row or 0)


def execute_request(
    client: httpx.Client,
    endpoint: EndpointProfile,
    plan: BenchmarkPlan,
    prompt: PromptRecord,
    *,
    measured: bool,
    source_row: int,
    config: dict[str, Any],
    redact: bool,
) -> BenchmarkSample:
    started_at = _iso_now(None)
    headers = dict(plan.workload.request.headers)
    if endpoint.request_overrides:
        headers.update(endpoint.request_overrides.headers)
    auth_headers, auth_error = _auth_headers(endpoint)
    headers.update(auth_headers)
    path = endpoint.request_overrides.path if endpoint.request_overrides and endpoint.request_overrides.path else plan.workload.request.path
    url = urljoin(endpoint.base_url.rstrip("/") + "/", path.lstrip("/"))
    streaming = endpoint.response_mode == "streaming"
    body = render_template(
        plan.workload.request.body_template,
        {
            "model_name": endpoint.model_name or plan.workload.model.declared_model_name,
            "prompt": prompt.prompt,
            "max_output_tokens": endpoint.capabilities.max_output_tokens or plan.workload.model.expected_output_tokens_p95 or 256,
            "streaming": streaming,
            "temperature": 0,
        },
    )
    request_bytes = len(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    if auth_error:
        return BenchmarkSample(
            endpoint_id=endpoint.endpoint_id,
            prompt_id=prompt.id,
            measured=measured,
            status="ERROR",
            started_at=started_at,
            response_mode=endpoint.response_mode,
            source_row=source_row,
            request_bytes=request_bytes,
            error_code="AUTH_ENV_MISSING",
            error_text_redacted="AUTH_ENV_MISSING",
        )
    start = time.perf_counter()
    try:
        if streaming:
            return _execute_streaming(client, endpoint, plan, prompt, url, headers, body, measured, source_row, config, redact, start, started_at, request_bytes)
        return _execute_non_streaming(client, endpoint, plan, prompt, url, headers, body, measured, source_row, config, redact, start, started_at, request_bytes)
    except httpx.TimeoutException as exc:
        return BenchmarkSample(
            endpoint_id=endpoint.endpoint_id,
            prompt_id=prompt.id,
            measured=measured,
            status="TIMEOUT",
            started_at=started_at,
            end_to_end_latency_ms=round((time.perf_counter() - start) * 1000, 4),
            timed_out=True,
            response_mode=endpoint.response_mode,
            source_row=source_row,
            request_bytes=request_bytes,
            error_code="REQUEST_TIMEOUT",
            error_text_redacted=redact_text(str(exc)),
        )
    except Exception as exc:
        return BenchmarkSample(
            endpoint_id=endpoint.endpoint_id,
            prompt_id=prompt.id,
            measured=measured,
            status="ERROR",
            started_at=started_at,
            end_to_end_latency_ms=round((time.perf_counter() - start) * 1000, 4),
            response_mode=endpoint.response_mode,
            source_row=source_row,
            request_bytes=request_bytes,
            error_code="REQUEST_FAILED",
            error_text_redacted=redact_text(str(exc)) if redact else redact_text(str(exc)),
        )


def _execute_non_streaming(
    client: httpx.Client,
    endpoint: EndpointProfile,
    plan: BenchmarkPlan,
    prompt: PromptRecord,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    measured: bool,
    source_row: int,
    config: dict[str, Any],
    redact: bool,
    start: float,
    started_at: str,
    request_bytes: int,
) -> BenchmarkSample:
    response = client.request(plan.workload.request.method, url, headers=headers, json=body)
    latency_ms = round((time.perf_counter() - start) * 1000, 4)
    response_bytes = len(response.content or b"")
    if response.status_code >= 400:
        return BenchmarkSample(
            endpoint_id=endpoint.endpoint_id,
            prompt_id=prompt.id,
            measured=measured,
            status="ERROR",
            http_status=response.status_code,
            started_at=started_at,
            end_to_end_latency_ms=latency_ms,
            response_mode=endpoint.response_mode,
            source_row=source_row,
            request_bytes=request_bytes,
            response_bytes=response_bytes,
            error_code="HTTP_ERROR",
            error_text_redacted=redact_text(response.text[:500]),
        )
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        return BenchmarkSample(
            endpoint_id=endpoint.endpoint_id,
            prompt_id=prompt.id,
            measured=measured,
            status="ERROR",
            http_status=response.status_code,
            started_at=started_at,
            end_to_end_latency_ms=latency_ms,
            response_mode=endpoint.response_mode,
            source_row=source_row,
            request_bytes=request_bytes,
            response_bytes=response_bytes,
            error_code="RESPONSE_PARSE_FAILED",
            error_text_redacted=redact_text(str(exc)),
        )
    extractors = plan.workload.response_extractors.non_streaming
    text, warnings = extract_json_path(payload, extractors.text_json_path if extractors else None)
    usage_in, warn_in = extract_json_path(payload, extractors.usage_input_tokens_json_path if extractors else None)
    usage_out, warn_out = extract_json_path(payload, extractors.usage_output_tokens_json_path if extractors else None)
    warnings.extend(warn_in if usage_in is None else [])
    warnings.extend(warn_out if usage_out is None else [])
    input_tokens, input_source = _token_value(usage_in, prompt, config)
    output_tokens, output_source = output_tokens_from_text(
        _as_int(usage_out),
        str(text or ""),
        prompt.expected_output_tokens_estimate,
        int(config.get("token_estimate_chars_per_token", 4)),
    )
    source = "EXACT_FROM_RESPONSE" if input_source == output_source == "EXACT_FROM_RESPONSE" else output_source
    return BenchmarkSample(
        endpoint_id=endpoint.endpoint_id,
        prompt_id=prompt.id,
        measured=measured,
        status="SUCCESS",
        http_status=response.status_code,
        started_at=started_at,
        end_to_end_latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        token_count_source=source,
        output_tokens_per_second=round(output_tokens / max(latency_ms / 1000, 0.000001), 4),
        request_bytes=request_bytes,
        response_bytes=response_bytes,
        response_mode=endpoint.response_mode,
        source_row=source_row,
        warnings=_sample_warnings(warnings, source),
    )


def _execute_streaming(
    client: httpx.Client,
    endpoint: EndpointProfile,
    plan: BenchmarkPlan,
    prompt: PromptRecord,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    measured: bool,
    source_row: int,
    config: dict[str, Any],
    redact: bool,
    start: float,
    started_at: str,
    request_bytes: int,
) -> BenchmarkSample:
    text_chunks: list[str] = []
    chunk_times: list[float] = []
    lines: list[str] = []
    response_bytes = 0
    status_code: int | None = None
    extractors = plan.workload.response_extractors.streaming
    with client.stream(plan.workload.request.method, url, headers=headers, json=body) as response:
        status_code = response.status_code
        for line in response.iter_lines():
            now = time.perf_counter()
            line_text = line.decode("utf-8") if isinstance(line, bytes) else line
            response_bytes += len(line_text.encode("utf-8"))
            lines.append(line_text)
            if line_text.strip().startswith("data:") and line_text.strip()[len("data:") :].strip() != "[DONE]":
                try:
                    payload = json.loads(line_text.strip()[len("data:") :].strip())
                except json.JSONDecodeError:
                    continue
                text, _ = extract_json_path(payload, extractors.event_text_json_path if extractors else None)
                if text:
                    text_chunks.append(str(text))
                    chunk_times.append(now)
    latency_ms = round((time.perf_counter() - start) * 1000, 4)
    if status_code is not None and status_code >= 400:
        return BenchmarkSample(
            endpoint_id=endpoint.endpoint_id,
            prompt_id=prompt.id,
            measured=measured,
            status="ERROR",
            http_status=status_code,
            started_at=started_at,
            end_to_end_latency_ms=latency_ms,
            response_mode=endpoint.response_mode,
            source_row=source_row,
            request_bytes=request_bytes,
            response_bytes=response_bytes,
            error_code="HTTP_ERROR",
            error_text_redacted="HTTP_ERROR",
        )
    parsed = parse_sse_lines(lines)
    usage_in = usage_out = None
    finish_seen = parsed.done_observed
    warnings = list(parsed.warnings)
    for payload in parsed.payloads:
        if extractors:
            finish, _ = extract_json_path(payload, extractors.finish_reason_json_path)
            if finish:
                finish_seen = True
            usage_in_value, _ = extract_json_path(payload, extractors.usage_input_tokens_json_path)
            usage_out_value, _ = extract_json_path(payload, extractors.usage_output_tokens_json_path)
            usage_in = usage_in if usage_in is not None else usage_in_value
            usage_out = usage_out if usage_out is not None else usage_out_value
    if finish_seen and "STREAM_FINISH_NOT_OBSERVED" in warnings:
        warnings.remove("STREAM_FINISH_NOT_OBSERVED")
    input_tokens, input_source = _token_value(usage_in, prompt, config)
    output_text = "".join(text_chunks)
    output_tokens, output_source = output_tokens_from_text(
        _as_int(usage_out),
        output_text,
        prompt.expected_output_tokens_estimate,
        int(config.get("token_estimate_chars_per_token", 4)),
    )
    source = "EXACT_FROM_RESPONSE" if input_source == output_source == "EXACT_FROM_RESPONSE" else output_source
    ttft_ms = round((chunk_times[0] - start) * 1000, 4) if chunk_times else None
    gaps_ms = [(chunk_times[idx] - chunk_times[idx - 1]) * 1000 for idx in range(1, len(chunk_times))]
    return BenchmarkSample(
        endpoint_id=endpoint.endpoint_id,
        prompt_id=prompt.id,
        measured=measured,
        status="SUCCESS",
        http_status=status_code,
        started_at=started_at,
        end_to_end_latency_ms=latency_ms,
        time_to_first_token_ms=ttft_ms,
        inter_token_latency_p50_ms=round(percentile(gaps_ms, 50), 4) if gaps_ms else None,
        inter_token_latency_p95_ms=round(percentile(gaps_ms, 95), 4) if gaps_ms else None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        token_count_source=source,
        output_tokens_per_second=round(output_tokens / max(latency_ms / 1000, 0.000001), 4),
        request_bytes=request_bytes,
        response_bytes=response_bytes,
        response_mode=endpoint.response_mode,
        source_row=source_row,
        warnings=_sample_warnings(warnings, source),
    )


def _auth_headers(endpoint: EndpointProfile) -> tuple[dict[str, str], str | None]:
    if endpoint.auth.type == "none":
        return {}, None
    token = os.environ.get(endpoint.auth.token_env or "")
    if not token:
        return {}, "AUTH_ENV_MISSING"
    if endpoint.auth.type == "bearer_env":
        return {"Authorization": f"Bearer {token}"}, None
    return {endpoint.auth.header_name or "Authorization": token}, None


def _token_value(usage_value: Any, prompt: PromptRecord, config: dict[str, Any]) -> tuple[int, str]:
    parsed = _as_int(usage_value)
    if parsed is not None:
        return parsed, "EXACT_FROM_RESPONSE"
    return input_tokens_from_prompt(prompt, int(config.get("token_estimate_chars_per_token", 4)))


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sample_warnings(warnings: list[str], token_source: str) -> list[str]:
    out = list(warnings)
    if token_source != "EXACT_FROM_RESPONSE":
        out.append("TOKEN_COUNTS_ESTIMATED")
    return _unique(out)


def _iso_now(now: str | None) -> str:
    if now:
        return now
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _unique(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if value not in seen:
            out.append(value)
            seen.add(value)
    return out


def write_results_json(results: BenchmarkResults, path: str) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    data = results.model_dump(mode="json", exclude={"samples"})
    output.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def load_results_json(path: str) -> BenchmarkResults:
    return BenchmarkResults.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
