from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .config import DEFAULT_CONFIG
from .constraints import load_constraints
from .endpoint_profile import load_endpoint_profiles
from .models import EndpointProfiles, UnitEconomics
from .prompt_packs import canonical_pack_name, write_prompt_pack
from .workload_profile import load_workload_profile


BUNDLE_TEMPLATES = {
    "customer-chat": {
        "workload_id": "customer_chat_preflight",
        "workload_type": "chat_text",
        "model_family": "chat",
        "prompt_pack": "customer_chat_short",
        "streaming_required": True,
        "measured_requests": 30,
        "warmup_requests": 3,
        "concurrency": 2,
        "context": 8192,
        "output_p95": 500,
        "latency_p95": 1200,
        "ttft_p95": 500,
        "inter_token_p95": 75,
    },
    "low-latency-chat": {
        "workload_id": "low_latency_chat_preflight",
        "workload_type": "chat_text",
        "model_family": "chat",
        "prompt_pack": "streaming_chat",
        "streaming_required": True,
        "measured_requests": 30,
        "warmup_requests": 3,
        "concurrency": 2,
        "context": 8192,
        "output_p95": 500,
        "latency_p95": 900,
        "ttft_p95": 250,
        "inter_token_p95": 50,
    },
    "cost-sensitive-embedding": {
        "workload_id": "embedding_cost_preflight",
        "workload_type": "embedding",
        "model_family": "embedding",
        "prompt_pack": "embedding_search",
        "streaming_required": False,
        "measured_requests": 40,
        "warmup_requests": 3,
        "concurrency": 4,
        "context": 2048,
        "output_p95": 0,
        "latency_p95": 800,
        "ttft_p95": None,
        "inter_token_p95": None,
    },
    "long-context-summarization": {
        "workload_id": "long_context_summary_preflight",
        "workload_type": "completion_text",
        "model_family": "completion",
        "prompt_pack": "summarization_long",
        "streaming_required": False,
        "measured_requests": 20,
        "warmup_requests": 2,
        "concurrency": 1,
        "context": 16384,
        "output_p95": 800,
        "latency_p95": 3500,
        "ttft_p95": None,
        "inter_token_p95": None,
    },
    "interactive-support-chat": {
        "workload_id": "interactive_support_chat_preflight",
        "workload_type": "chat_text",
        "model_family": "chat",
        "prompt_pack": "interactive_support_chat",
        "streaming_required": True,
        "measured_requests": 36,
        "warmup_requests": 4,
        "concurrency": 3,
        "context": 8192,
        "output_p95": 450,
        "latency_p95": 1000,
        "ttft_p95": 300,
        "inter_token_p95": 60,
    },
    "agent-tool-summary": {
        "workload_id": "agent_tool_summary_preflight",
        "workload_type": "chat_text",
        "model_family": "chat",
        "prompt_pack": "agent_tool_summary",
        "streaming_required": False,
        "measured_requests": 30,
        "warmup_requests": 3,
        "concurrency": 2,
        "context": 8192,
        "output_p95": 350,
        "latency_p95": 1400,
        "ttft_p95": None,
        "inter_token_p95": None,
    },
    "batch-document-summary": {
        "workload_id": "batch_document_summary_preflight",
        "workload_type": "completion_text",
        "model_family": "completion",
        "prompt_pack": "batch_document_summary",
        "streaming_required": False,
        "measured_requests": 30,
        "warmup_requests": 2,
        "concurrency": 3,
        "context": 16384,
        "output_p95": 700,
        "latency_p95": 4500,
        "ttft_p95": None,
        "inter_token_p95": None,
    },
    "classification-triage": {
        "workload_id": "classification_triage_preflight",
        "workload_type": "chat_text",
        "model_family": "chat",
        "prompt_pack": "classification_triage",
        "streaming_required": False,
        "measured_requests": 50,
        "warmup_requests": 5,
        "concurrency": 5,
        "context": 4096,
        "output_p95": 80,
        "latency_p95": 900,
        "ttft_p95": None,
        "inter_token_p95": None,
    },
    "location-blocked-fastest": {
        "workload_id": "location_blocked_fastest_preflight",
        "workload_type": "chat_text",
        "model_family": "chat",
        "prompt_pack": "interactive_support_chat",
        "streaming_required": True,
        "measured_requests": 24,
        "warmup_requests": 2,
        "concurrency": 2,
        "context": 8192,
        "output_p95": 450,
        "latency_p95": 1100,
        "ttft_p95": 350,
        "inter_token_p95": 70,
        "allowed_regions": ["region-b"],
        "allowed_data_zones": ["ca-zone-2"],
        "scenario": "fastest_location_blocked",
    },
    "cheapest-latency-risk": {
        "workload_id": "cheapest_latency_risk_preflight",
        "workload_type": "chat_text",
        "model_family": "chat",
        "prompt_pack": "customer_chat_short",
        "streaming_required": False,
        "measured_requests": 24,
        "warmup_requests": 2,
        "concurrency": 2,
        "context": 8192,
        "output_p95": 450,
        "latency_p95": 900,
        "ttft_p95": None,
        "inter_token_p95": None,
        "scenario": "cheap_misses_latency",
    },
    "streaming-required-missing": {
        "workload_id": "streaming_required_missing_preflight",
        "workload_type": "chat_text",
        "model_family": "chat",
        "prompt_pack": "streaming_chat",
        "streaming_required": True,
        "measured_requests": 24,
        "warmup_requests": 2,
        "concurrency": 2,
        "context": 8192,
        "output_p95": 450,
        "latency_p95": 1100,
        "ttft_p95": 400,
        "inter_token_p95": 75,
        "scenario": "streaming_mixed",
    },
    "high-timeout-review": {
        "workload_id": "high_timeout_review_preflight",
        "workload_type": "chat_text",
        "model_family": "chat",
        "prompt_pack": "agent_tool_summary",
        "streaming_required": False,
        "measured_requests": 30,
        "warmup_requests": 3,
        "concurrency": 2,
        "context": 8192,
        "output_p95": 350,
        "latency_p95": 1600,
        "ttft_p95": None,
        "inter_token_p95": None,
        "scenario": "timeout_risk",
    },
    "no-passing-endpoints": {
        "workload_id": "no_passing_endpoints_preflight",
        "workload_type": "chat_text",
        "model_family": "chat",
        "prompt_pack": "customer_chat_short",
        "streaming_required": False,
        "measured_requests": 18,
        "warmup_requests": 2,
        "concurrency": 2,
        "context": 8192,
        "output_p95": 450,
        "latency_p95": 50,
        "ttft_p95": None,
        "inter_token_p95": None,
        "scenario": "no_passing_latency",
    },
}
TEMPLATE_ALIASES = {
    "regional-low-latency": "low-latency-chat",
    "low-cost-embedding": "cost-sensitive-embedding",
    "summary-review": "long-context-summarization",
    "retrieval-embedding": "cost-sensitive-embedding",
    "document-summary": "batch-document-summary",
    "support-chat": "interactive-support-chat",
}


def init_bundle(output_dir: str | Path, template: str = "customer-chat", prompt_count: int = 100, seed: int = 12345) -> dict[str, Path]:
    template_key, cfg = _template_config(template)
    root = Path(output_dir)
    paths = bundle_paths(root)
    for path in paths.values():
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
    write_prompt_pack(paths["prompts"], cfg["prompt_pack"], count=prompt_count, seed=seed)
    paths["workload"].write_text(yaml.safe_dump(_workload(cfg), sort_keys=False), encoding="utf-8")
    paths["endpoints"].write_text(yaml.safe_dump(_endpoints(cfg), sort_keys=False), encoding="utf-8")
    paths["constraints"].write_text(yaml.safe_dump(_constraints(cfg), sort_keys=False), encoding="utf-8")
    paths["thresholds"].write_text(yaml.safe_dump(DEFAULT_CONFIG, sort_keys=False), encoding="utf-8")
    paths["rate_cards"].write_text(yaml.safe_dump(_rate_cards(), sort_keys=False), encoding="utf-8")
    paths["data_inventory"].write_text(yaml.safe_dump(_data_inventory(template_key, prompt_count, seed), sort_keys=False), encoding="utf-8")
    paths["request_streaming"].write_text(yaml.safe_dump(_request_template(streaming=True), sort_keys=False), encoding="utf-8")
    paths["request_non_streaming"].write_text(yaml.safe_dump(_request_template(streaming=False), sort_keys=False), encoding="utf-8")
    paths["runbook"].write_text(_runbook(cfg), encoding="utf-8")
    return paths


def bundle_paths(root: str | Path) -> dict[str, Path]:
    base = Path(root)
    return {
        "root": base,
        "workload": base / "workload.yml",
        "endpoints": base / "endpoints.yml",
        "constraints": base / "constraints.yml",
        "thresholds": base / "thresholds.yml",
        "prompts": base / "prompts" / "prompts.jsonl",
        "rate_cards": base / "rate_cards.yml",
        "data_inventory": base / "data_inventory.yml",
        "request_streaming": base / "request_templates" / "http_json_streaming_sse.yml",
        "request_non_streaming": base / "request_templates" / "http_json_non_streaming.yml",
        "runbook": base / "runbook.md",
    }


def validate_bundle(root: str | Path) -> tuple[list[str], list[str]]:
    paths = bundle_paths(root)
    errors: list[str] = []
    warnings: list[str] = []
    required = ["workload", "endpoints", "constraints", "thresholds", "prompts", "rate_cards", "data_inventory", "runbook"]
    for key in required:
        if not paths[key].exists():
            errors.append(f"MISSING_{key.upper()}")
    if errors:
        return errors, warnings
    workload = load_workload_profile(str(paths["workload"]))
    endpoint_profiles = load_endpoint_profiles(str(paths["endpoints"]))
    apply_rate_cards(endpoint_profiles, paths["rate_cards"])
    load_constraints(str(paths["constraints"]))
    prompt_count = sum(1 for line in paths["prompts"].read_text(encoding="utf-8").splitlines() if line.strip())
    if prompt_count < workload.benchmark.measured_requests:
        warnings.append("PROMPT_COUNT_BELOW_MEASURED_REQUESTS")
    inventory = yaml.safe_load(paths["data_inventory"].read_text(encoding="utf-8")) or {}
    if inventory.get("contains_sensitive_data") is not False:
        warnings.append("DATA_INVENTORY_REQUIRES_REVIEW")
    return errors, warnings


def apply_rate_cards(endpoint_profiles: EndpointProfiles, rate_cards_path: str | Path) -> EndpointProfiles:
    path = Path(rate_cards_path)
    if not path.exists():
        return endpoint_profiles
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    default_currency = data.get("currency")
    raw_cards = data.get("rate_cards") or []
    cards: dict[str, UnitEconomics] = {}
    for raw_card in raw_cards:
        if not isinstance(raw_card, dict):
            continue
        endpoint_id = raw_card.get("endpoint_id")
        if not endpoint_id:
            continue
        payload = {key: value for key, value in raw_card.items() if key != "endpoint_id"}
        if default_currency and payload.get("currency") is None:
            payload["currency"] = default_currency
        cards[str(endpoint_id)] = UnitEconomics.model_validate(payload)
    if not cards:
        return endpoint_profiles
    endpoints = [
        endpoint.model_copy(update={"unit_economics": cards.get(endpoint.endpoint_id, endpoint.unit_economics)})
        for endpoint in endpoint_profiles.endpoints
    ]
    return EndpointProfiles(endpoints=endpoints)


def write_simulated_endpoints(bundle_root: str | Path, output: str | Path) -> None:
    paths = bundle_paths(bundle_root)
    endpoint_profiles = apply_rate_cards(load_endpoint_profiles(str(paths["endpoints"])), paths["rate_cards"])
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(endpoint_profiles.model_dump(mode="json"), sort_keys=False), encoding="utf-8")


def write_generated_constraints(output: str | Path, policy_pack: str = "customer-chat") -> None:
    _, cfg = _template_config(policy_pack)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(_constraints(cfg), sort_keys=False), encoding="utf-8")


def input_hashes(root: str | Path) -> dict[str, str]:
    base = Path(root)
    hashes: dict[str, str] = {}
    for path in sorted(base.rglob("*")):
        if path.is_file():
            hashes[str(path.relative_to(base))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def write_decision_bundle(
    output_dir: str | Path,
    *,
    input_bundle: str | Path | None,
    results_path: str | Path | None,
    recommendation_json: str,
    recommendation_markdown: str,
    executive_summary_markdown: str | None = None,
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "recommendation.json").write_text(recommendation_json, encoding="utf-8")
    (output / "recommendation.md").write_text(recommendation_markdown, encoding="utf-8")
    if executive_summary_markdown is not None:
        (output / "executive_summary.md").write_text(executive_summary_markdown, encoding="utf-8")
    manifest: dict[str, Any] = {
        "bundle_version": 1,
        "review_only": True,
        "includes_results": results_path is not None,
        "includes_input_hashes": input_bundle is not None,
        "includes_executive_summary": executive_summary_markdown is not None,
    }
    if results_path:
        result_source = Path(results_path)
        if result_source.exists():
            (output / "results.json").write_text(result_source.read_text(encoding="utf-8"), encoding="utf-8")
    if input_bundle:
        hashes = input_hashes(input_bundle)
        (output / "input_hashes.json").write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "bundle_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _workload(cfg: dict[str, Any]) -> dict[str, Any]:
    streaming = bool(cfg["streaming_required"])
    request = _request_template(streaming=streaming)["request"]
    extractors = _extractors()
    if cfg["workload_type"] == "embedding":
        request = {
            "method": "POST",
            "path": "/v1/embeddings",
            "headers": {"Content-Type": "application/json"},
            "body_template": {"model": "{{model_name}}", "input": "{{prompt}}"},
        }
        extractors["non_streaming"]["text_json_path"] = "$.data[0].embedding"
    return {
        "workload_id": cfg["workload_id"],
        "display_name": "Generated synthetic workload profile",
        "workload_type": cfg["workload_type"],
        "model": {
            "declared_model_name": f"generic-{cfg['model_family']}-model",
            "model_family": cfg["model_family"],
            "min_context_window_tokens": cfg["context"],
            "expected_input_tokens_p50": max(100, int(cfg["context"] * 0.08)),
            "expected_input_tokens_p95": max(200, int(cfg["context"] * 0.2)),
            "expected_output_tokens_p50": max(0, int(cfg["output_p95"] * 0.4)),
            "expected_output_tokens_p95": cfg["output_p95"],
            "streaming_required": streaming,
        },
        "benchmark": {
            "prompt_file": "prompts/prompts.jsonl",
            "warmup_requests": cfg["warmup_requests"],
            "measured_requests": cfg["measured_requests"],
            "concurrency": cfg["concurrency"],
            "request_timeout_seconds": 60,
            "random_seed": 12345,
        },
        "request": request,
        "response_extractors": extractors,
    }


def _endpoints(cfg: dict[str, Any]) -> dict[str, Any]:
    workload_type = cfg["workload_type"]
    streaming = bool(cfg["streaming_required"])
    scenario = cfg.get("scenario", "standard")
    fast_streaming = streaming
    balanced_streaming = streaming
    low_cost_streaming = streaming
    fast_latency = 22
    balanced_latency = 35
    low_cost_latency = 65
    fast_timeout = 0.0
    balanced_timeout = 0.0
    low_cost_timeout = 0.0
    if scenario == "cheap_misses_latency":
        fast_latency = 260
        balanced_latency = 520
        low_cost_latency = 1400
    elif scenario == "streaming_mixed":
        fast_streaming = False
        balanced_streaming = True
        low_cost_streaming = False
    elif scenario == "timeout_risk":
        balanced_timeout = 40.0
        low_cost_timeout = 50.0
    elif scenario == "no_passing_latency":
        fast_latency = 90
        balanced_latency = 125
        low_cost_latency = 180
    return {
        "endpoints": [
            _endpoint(
                "candidate_fast",
                "region-a",
                "ca-zone-1",
                "local",
                workload_type,
                fast_streaming,
                fast_latency,
                8,
                4,
                1.40,
                4.50,
                timeout_rate_pct=fast_timeout,
            ),
            _endpoint(
                "candidate_balanced",
                "region-b",
                "ca-zone-2",
                "partner",
                workload_type,
                balanced_streaming,
                balanced_latency,
                12,
                6,
                1.10,
                3.80,
                timeout_rate_pct=balanced_timeout,
            ),
            _endpoint(
                "candidate_low_cost",
                "region-b",
                "ca-zone-2",
                "partner",
                workload_type,
                low_cost_streaming,
                low_cost_latency,
                20,
                9,
                0.65,
                2.20,
                timeout_rate_pct=low_cost_timeout,
            ),
        ]
    }


def _endpoint(
    endpoint_id: str,
    region: str,
    zone: str,
    operator_control: str,
    workload_type: str,
    streaming: bool,
    latency_ms: float,
    ttft_ms: float,
    inter_token_ms: float,
    input_rate: float,
    output_rate: float,
    *,
    error_rate_pct: float = 0.0,
    timeout_rate_pct: float = 0.0,
) -> dict[str, Any]:
    response_mode = "streaming" if streaming else "non_streaming"
    path = "/v1/chat/completions" if workload_type == "chat_text" else "/v1/embeddings" if workload_type == "embedding" else "/v1/completions"
    return {
        "endpoint_id": endpoint_id,
        "display_name": f"{endpoint_id} inference endpoint",
        "base_url": f"https://{endpoint_id}.example.invalid",
        "model_name": "generic-model",
        "protocol": "http_json",
        "response_mode": response_mode,
        "auth": {"type": "none"},
        "declared_location": {
            "country": "CA",
            "region": region,
            "data_zone": zone,
            "operator_control": operator_control,
        },
        "capabilities": {
            "workload_types": [workload_type, "chat_text", "completion_text", "embedding"],
            "streaming": streaming,
            "max_context_window_tokens": 32768,
            "max_output_tokens": 2048,
        },
        "unit_economics": {
            "currency": "CAD",
            "input_per_1m_tokens": input_rate,
            "output_per_1m_tokens": output_rate,
            "per_1k_requests": 0.0,
            "notes": "User-supplied example numbers only.",
        },
        "request_overrides": {"path": path, "headers": {"X-Endpoint-Profile": endpoint_id}},
        "simulator": {
            "enabled": True,
            "latency_ms": latency_ms,
            "time_to_first_token_ms": ttft_ms,
            "inter_token_latency_ms": inter_token_ms,
            "input_tokens": 120,
            "output_tokens": 48 if workload_type != "embedding" else 0,
            "error_rate_pct": error_rate_pct,
            "timeout_rate_pct": timeout_rate_pct,
            "response_text": "Synthetic response text generated by the local fake endpoint simulator.",
        },
    }


def _constraints(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "constraint_id": f"{cfg['workload_id']}_constraints",
        "data_location": {
            "allowed_countries": cfg.get("allowed_countries", ["CA"]),
            "allowed_regions": cfg.get("allowed_regions", ["region-a", "region-b"]),
            "allowed_data_zones": cfg.get("allowed_data_zones", ["ca-zone-1", "ca-zone-2"]),
            "allowed_operator_control": cfg.get("allowed_operator_control", ["local", "partner"]),
            "require_declared_location": True,
        },
        "latency_targets": {
            "end_to_end_p95_ms": cfg["latency_p95"],
            "time_to_first_token_p95_ms": cfg["ttft_p95"],
            "inter_token_latency_p95_ms": cfg["inter_token_p95"],
        },
        "throughput_targets": {
            "min_requests_per_second": 0.5,
            "min_output_tokens_per_second": 10 if cfg["workload_type"] != "embedding" else None,
        },
        "reliability_targets": {"max_error_rate_pct": 1.0, "max_timeout_rate_pct": 1.0},
        "economics": {
            "currency": "CAD",
            "prefer_lower_cost_when_within_latency_margin_pct": 10,
            "max_estimated_cost_per_1k_requests": None,
            "max_estimated_cost_per_1m_output_tokens": None,
        },
        "recommendation": {
            "objective": cfg.get("objective", "balanced"),
            "weights": cfg.get("weights", {"latency": 40, "throughput": 20, "economics": 20, "data_location": 20}),
        },
    }


def _request_template(streaming: bool) -> dict[str, Any]:
    if streaming:
        body = {
            "model": "{{model_name}}",
            "messages": [
                {"role": "system", "content": "You are a concise assistant."},
                {"role": "user", "content": "{{prompt}}"},
            ],
            "temperature": 0,
            "max_tokens": "{{max_output_tokens}}",
            "stream": "{{streaming}}",
        }
        path = "/v1/chat/completions"
    else:
        body = {
            "model": "{{model_name}}",
            "input": "{{prompt}}",
            "temperature": 0,
            "max_tokens": "{{max_output_tokens}}",
            "stream": "{{streaming}}",
        }
        path = "/v1/completions"
    return {"request": {"method": "POST", "path": path, "headers": {"Content-Type": "application/json"}, "body_template": body}}


def _extractors() -> dict[str, Any]:
    return {
        "non_streaming": {
            "text_json_path": "$.choices[0].message.content",
            "usage_input_tokens_json_path": "$.usage.prompt_tokens",
            "usage_output_tokens_json_path": "$.usage.completion_tokens",
        },
        "streaming": {
            "event_text_json_path": "$.choices[0].delta.content",
            "finish_reason_json_path": "$.choices[0].finish_reason",
            "usage_input_tokens_json_path": "$.usage.prompt_tokens",
            "usage_output_tokens_json_path": "$.usage.completion_tokens",
        },
    }


def _rate_cards() -> dict[str, Any]:
    return {
        "currency": "CAD",
        "rate_cards": [
            {"endpoint_id": "candidate_fast", "input_per_1m_tokens": 1.40, "output_per_1m_tokens": 4.50, "per_1k_requests": 0.0},
            {"endpoint_id": "candidate_balanced", "input_per_1m_tokens": 1.10, "output_per_1m_tokens": 3.80, "per_1k_requests": 0.0},
            {"endpoint_id": "candidate_low_cost", "input_per_1m_tokens": 0.65, "output_per_1m_tokens": 2.20, "per_1k_requests": 0.0},
        ],
        "notes": "Example user-supplied rate cards for offline demonstration.",
    }


def _data_inventory(template: str, prompt_count: int, seed: int) -> dict[str, Any]:
    return {
        "template": template,
        "prompt_count": prompt_count,
        "prompt_pack": canonical_pack_name(BUNDLE_TEMPLATES[template]["prompt_pack"]),
        "synthetic_prompts": True,
        "contains_sensitive_data": False,
        "contains_personal_data": False,
        "contains_credentials": False,
        "authorized_for_benchmark": True,
        "generator": "deterministic_template_v1",
        "seed": seed,
    }


def _runbook(cfg: dict[str, Any]) -> str:
    return f"""# Benchmark Input Bundle Runbook

This bundle is generated for review-only benchmark use.

```bash
inference-placement-bench validate-bundle --input .
inference-placement-bench evaluate --bundle . --output-bundle out/decision_bundle --no-network
```

Workload ID: `{cfg["workload_id"]}`

The included endpoints use the local fake endpoint simulator. `rate_cards.yml` is the authoritative economics input for generated bundles. Replace endpoint URLs, auth declarations, declared locations, capabilities, simulator settings, and user-supplied rate cards before benchmarking real candidate endpoints.
"""


def _template_config(template: str) -> tuple[str, dict[str, Any]]:
    key = TEMPLATE_ALIASES.get(template, template)
    cfg = BUNDLE_TEMPLATES.get(key)
    if cfg is None:
        raise ValueError(f"unknown bundle template: {template}")
    return key, cfg
