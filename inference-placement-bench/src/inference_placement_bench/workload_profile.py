from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import PromptRecord, WorkloadProfile


SENSITIVE_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]"),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._-]+"),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    re.compile(r"\b\d{13,19}\b"),
]


def load_workload_profile(path: str) -> WorkloadProfile:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return WorkloadProfile.model_validate(data)


def validate_workload_profile(path: str) -> tuple[WorkloadProfile | None, list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    try:
        workload = load_workload_profile(path)
    except (OSError, ValidationError, yaml.YAMLError, ValueError) as exc:
        return None, warnings, [f"WORKLOAD_PROFILE_INVALID: {exc}"]
    if workload.workload_type not in {"chat_text", "completion_text", "embedding"}:
        warnings.append("WORKLOAD_TYPE_NOT_IMPLEMENTED")
    return workload, warnings, errors


def _looks_sensitive(text: str) -> bool:
    return any(pattern.search(text) for pattern in SENSITIVE_PATTERNS)


def load_prompt_file(path: str) -> list[PromptRecord]:
    prompt_path = Path(path)
    prompts: list[PromptRecord] = []
    with prompt_path.open("r", encoding="utf-8") as handle:
        for row_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL row {row_number}: {exc}") from exc
            if "prompt" not in payload:
                raise ValueError(f"prompt is required on row {row_number}")
            prompt_id = payload.get("id") or f"prompt_{len(prompts) + 1:03d}"
            warnings = []
            if _looks_sensitive(str(payload["prompt"])):
                warnings.append("PROMPT_MAY_CONTAIN_SENSITIVE_DATA")
            prompts.append(
                PromptRecord(
                    id=str(prompt_id),
                    prompt=str(payload["prompt"]),
                    input_tokens_estimate=payload.get("input_tokens_estimate"),
                    expected_output_tokens_estimate=payload.get("expected_output_tokens_estimate"),
                    metadata=payload.get("metadata") or {},
                    warnings=warnings,
                )
            )
    if not prompts:
        raise ValueError("prompt file contains no prompts")
    return prompts


def synthetic_prompts(workload_type: str, count: int) -> list[PromptRecord]:
    templates = {
        "chat_text": [
            "Summarize this synthetic support request and draft a concise response.",
            "Classify this generic support message by urgency and provide one next step.",
            "Extract the requested action from this synthetic customer question.",
            "Rewrite this short synthetic policy note in plain language.",
        ],
        "completion_text": [
            "Continue this neutral operational note with one concise paragraph:",
            "Complete this synthetic status update using generic wording:",
            "Finish this short planning sentence with a practical next step:",
        ],
        "embedding": [
            "Synthetic document about account setup steps.",
            "Synthetic note about endpoint latency measurement.",
            "Synthetic snippet about location constraints and review.",
        ],
    }
    choices = templates.get(workload_type, templates["chat_text"])
    prompts: list[PromptRecord] = []
    for idx in range(count):
        text = choices[idx % len(choices)]
        prompts.append(
            PromptRecord(
                id=f"synthetic_{idx + 1:03d}",
                prompt=text,
                input_tokens_estimate=max(1, (len(text) + 3) // 4),
                expected_output_tokens_estimate=64,
                warnings=["SYNTHETIC_PROMPTS_USED"],
            )
        )
    return prompts


def load_or_generate_prompts(workload: WorkloadProfile, base_dir: str | Path = ".") -> list[PromptRecord]:
    if workload.benchmark.prompt_file:
        prompt_path = Path(workload.benchmark.prompt_file)
        if not prompt_path.is_absolute():
            prompt_path = Path(base_dir) / prompt_path
        return load_prompt_file(str(prompt_path))
    assert workload.benchmark.synthetic_prompt_count is not None
    return synthetic_prompts(workload.workload_type, workload.benchmark.synthetic_prompt_count)
