from __future__ import annotations

import json
from pathlib import Path


PROMPT_PACK_ALIASES = {
    "customer-chat": "customer_chat_short",
    "low-latency-chat": "customer_chat_short",
    "streaming-chat": "streaming_chat",
    "interactive-support-chat": "interactive_support_chat",
    "agent-tool-summary": "agent_tool_summary",
    "batch-document-summary": "batch_document_summary",
    "cost-sensitive-embedding": "embedding_search",
    "retrieval-embedding": "embedding_search",
    "long-context-summarization": "summarization_long",
    "classification-triage": "classification_triage",
}


def canonical_pack_name(name: str) -> str:
    return PROMPT_PACK_ALIASES.get(name, name)


def generate_prompt_rows(pack_name: str, count: int = 100, seed: int = 12345) -> list[dict]:
    pack = canonical_pack_name(pack_name)
    if count <= 0:
        raise ValueError("prompt count must be > 0")
    rows = []
    for idx in range(count):
        prompt_id = f"{_prefix(pack)}_{idx + 1:03d}"
        prompt, shape, input_tokens, output_tokens = _prompt_for(pack, idx, seed)
        rows.append(
            {
                "id": prompt_id,
                "prompt": prompt,
                "shape": shape,
                "synthetic": True,
                "input_tokens_estimate": input_tokens,
                "expected_output_tokens_estimate": output_tokens,
                "sensitivity": "none",
                "metadata": {
                    "generator": "deterministic_template_v1",
                    "seed": seed,
                    "prompt_index": idx + 1,
                    "synthetic": True,
                    "prompt_shape": shape,
                    "business_task": _business_task(pack),
                    "business_impact": _business_impact(pack),
                    "data_sensitivity": "none",
                },
            }
        )
    return rows


def write_prompt_pack(path: str | Path, pack_name: str, count: int = 100, seed: int = 12345) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = generate_prompt_rows(pack_name, count=count, seed=seed)
    output.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _prefix(pack: str) -> str:
    return {
        "customer_chat_short": "chat_short",
        "interactive_support_chat": "support_chat",
        "streaming_chat": "stream_chat",
        "summarization_long": "summary_long",
        "batch_document_summary": "batch_summary",
        "embedding_search": "embed",
        "classification": "classify",
        "classification_triage": "triage",
        "agent_tool_summary": "tool_summary",
        "completion_text": "complete",
    }.get(pack, "prompt")


def _prompt_for(pack: str, idx: int, seed: int) -> tuple[str, str, int, int]:
    variant = (idx + seed) % 7
    if pack in {"customer_chat_short", "streaming_chat", "interactive_support_chat"}:
        tasks = [
            "Summarize a synthetic support request and draft one concise response.",
            "Classify a generic support message by urgency and give one next action.",
            "Extract the requested action from a synthetic service question.",
            "Rewrite a short synthetic policy note in plain language.",
            "Create a brief acknowledgement for a generic support conversation.",
            "Identify missing information in a synthetic troubleshooting request.",
            "Turn a synthetic status note into a customer-facing update.",
        ]
        prompt = f"{tasks[variant]} Use neutral wording and avoid names, secrets, or real account details. Scenario {idx + 1}."
        shape = "short_chat" if pack == "customer_chat_short" else "streaming_chat" if pack == "streaming_chat" else "interactive_support_chat"
        return prompt, shape, 80 + variant * 12, 45 + variant * 5
    if pack in {"summarization_long", "batch_document_summary"}:
        section = (
            "This synthetic operations paragraph describes a generic process, an observed delay, "
            "a proposed mitigation, and a follow-up owner placeholder. "
        )
        repetitions = (18 + (variant * 4)) if pack == "summarization_long" else (8 + variant * 3)
        prompt = (
            "Summarize the following synthetic operations note into five concise bullets and call out open questions.\n\n"
            + section * repetitions
        )
        shape = "long_context_summarization" if pack == "summarization_long" else "batch_document_summary"
        return prompt, shape, 650 + repetitions * 22, 160
    if pack == "embedding_search":
        topics = [
            "account setup steps",
            "latency measurement notes",
            "declared location review",
            "rate-card comparison",
            "timeout handling",
            "streaming response behavior",
            "synthetic prompt governance",
        ]
        prompt = f"Synthetic document snippet about {topics[variant]} for retrieval testing item {idx + 1}."
        return prompt, "embedding_snippet", 24 + variant * 3, 0
    if pack in {"classification", "classification_triage"}:
        prompt = f"Classify this synthetic ticket as low, medium, or high urgency: generic request number {idx + 1} needs review."
        return prompt, "classification_triage" if pack == "classification_triage" else "classification", 32, 4
    if pack == "agent_tool_summary":
        prompt = (
            "Summarize these synthetic tool results for an internal operator. "
            f"Include status, blocker, and next action. Tool run {idx + 1}: latency check completed, one endpoint needs review, no real identifiers included."
        )
        return prompt, "agent_tool_summary", 90 + variant * 8, 70
    if pack == "completion_text":
        prompt = f"Continue this synthetic planning note with one operational next step: item {idx + 1} requires"
        return prompt, "completion", 28, 32
    prompt = f"Generic synthetic prompt {idx + 1} for benchmark input generation."
    return prompt, "generic", 24, 24


def _business_task(pack: str) -> str:
    return {
        "customer_chat_short": "customer-support-response",
        "interactive_support_chat": "interactive-support-response",
        "streaming_chat": "low-latency-streaming-chat",
        "summarization_long": "long-context-summary",
        "batch_document_summary": "batch-document-summary",
        "embedding_search": "retrieval-indexing",
        "classification": "ticket-classification",
        "classification_triage": "operations-triage-classification",
        "agent_tool_summary": "agent-tool-result-summary",
        "completion_text": "completion-generation",
    }.get(pack, "generic-inference")


def _business_impact(pack: str) -> str:
    return {
        "customer_chat_short": "user-experience-and-cost-screening",
        "interactive_support_chat": "frontline-response-latency-screening",
        "streaming_chat": "perceived-responsiveness-screening",
        "summarization_long": "review-cycle-time-screening",
        "batch_document_summary": "offline-throughput-and-cost-screening",
        "embedding_search": "retrieval-cost-and-latency-screening",
        "classification": "triage-throughput-screening",
        "classification_triage": "operations-prioritization-screening",
        "agent_tool_summary": "operator-workflow-latency-screening",
        "completion_text": "completion-latency-screening",
    }.get(pack, "placement-screening")
