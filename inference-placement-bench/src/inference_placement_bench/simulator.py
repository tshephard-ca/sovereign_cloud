from __future__ import annotations

import json
import threading
import time
from urllib.parse import urlparse

import httpx

from .models import BenchmarkPlan, EndpointProfile, EndpointSimulator


class DelayedSSEStream(httpx.SyncByteStream):
    def __init__(self, simulator: EndpointSimulator):
        self.simulator = simulator

    def __iter__(self):
        first_delay = self.simulator.time_to_first_token_ms / 1000
        if first_delay:
            time.sleep(first_delay)
        chunks = _response_chunks(self.simulator.response_text)
        for idx, chunk in enumerate(chunks):
            if idx > 0 and self.simulator.inter_token_latency_ms:
                time.sleep(self.simulator.inter_token_latency_ms / 1000)
            payload = {"choices": [{"delta": {"content": chunk}, "finish_reason": None}]}
            yield f"data: {json.dumps(payload)}\n\n".encode("utf-8")
        finish = {
            "choices": [{"delta": {}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": self.simulator.input_tokens,
                "completion_tokens": self.simulator.output_tokens,
            },
        }
        yield f"data: {json.dumps(finish)}\n\n".encode("utf-8")
        yield b"data: [DONE]\n\n"


class SimulatorTransport(httpx.BaseTransport):
    def __init__(self, endpoints: list[EndpointProfile]):
        self._by_host: dict[str, EndpointProfile] = {}
        for endpoint in endpoints:
            if endpoint.simulator and endpoint.simulator.enabled:
                host = urlparse(endpoint.base_url).hostname
                if host:
                    self._by_host[host] = endpoint
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        endpoint = self._by_host.get(request.url.host or "")
        if endpoint is None or endpoint.simulator is None:
            return httpx.Response(599, request=request, text="simulator endpoint not configured")
        simulator = endpoint.simulator
        count = self._next_count(endpoint.endpoint_id)
        if _deterministic_hit(simulator.timeout_rate_pct, count):
            raise httpx.ReadTimeout("simulated request timeout", request=request)
        if _deterministic_hit(simulator.error_rate_pct, count):
            return httpx.Response(503, request=request, text="simulated endpoint error")
        if endpoint.response_mode == "streaming":
            return httpx.Response(
                200,
                request=request,
                headers={"Content-Type": "text/event-stream"},
                stream=DelayedSSEStream(simulator),
            )
        if simulator.latency_ms:
            time.sleep(simulator.latency_ms / 1000)
        payload = _non_streaming_payload(endpoint, simulator, request.url.path)
        return httpx.Response(200, request=request, json=payload)

    def _next_count(self, endpoint_id: str) -> int:
        with self._lock:
            self._counts[endpoint_id] = self._counts.get(endpoint_id, 0) + 1
            return self._counts[endpoint_id]


def simulator_transport_for_plan(plan: BenchmarkPlan) -> SimulatorTransport | None:
    if any(endpoint.simulator and endpoint.simulator.enabled for endpoint in plan.endpoint_profiles):
        return SimulatorTransport(plan.endpoint_profiles)
    return None


def _non_streaming_payload(endpoint: EndpointProfile, simulator: EndpointSimulator, request_path: str) -> dict:
    if "embedding" in request_path:
        return {
            "data": [{"embedding": [0.01, 0.02, 0.03]}],
            "usage": {
                "prompt_tokens": simulator.input_tokens,
                "completion_tokens": 0,
            },
        }
    return {
        "choices": [{"message": {"content": simulator.response_text}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": simulator.input_tokens,
            "completion_tokens": simulator.output_tokens,
        },
    }


def _response_chunks(text: str) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    chunks = []
    for idx in range(0, len(words), 3):
        chunk = " ".join(words[idx : idx + 3])
        if idx + 3 < len(words):
            chunk += " "
        chunks.append(chunk)
    return chunks


def _deterministic_hit(rate_pct: float, count: int) -> bool:
    if rate_pct <= 0:
        return False
    if rate_pct >= 100:
        return True
    period = max(1, round(100 / rate_pct))
    return count % period == 0
