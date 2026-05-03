"""Lightweight JSON path extraction for endpoint responses."""

from __future__ import annotations

from typing import Any

from .models import EndpointProfile, ExtractedResponse


def extract_response(payload: Any, profile: EndpointProfile) -> ExtractedResponse:
    warnings: list[str] = []
    extractors = profile.response_extractors
    answer_values = json_path(payload, extractors.answer_text_json_path)
    answer_text = _string_join(answer_values)
    if not answer_text:
        warnings.append("ANSWER_TEXT_MISSING")
    citations = json_path(payload, extractors.citations_json_path)
    citations_list = _as_object_list(citations)
    if not citations_list:
        warnings.append("CITATIONS_MISSING")
    citation_doc_ids = _extract_from_items(citations_list, extractors.citation_doc_id_json_path, warnings)
    citation_titles = _extract_from_items(citations_list, extractors.citation_title_json_path, warnings)
    citation_snippets = _extract_from_items(citations_list, extractors.citation_snippet_json_path, warnings)
    metadata_values = _flatten_strings(json_path(payload, extractors.metadata_json_path))
    raw_context = _string_join(json_path(payload, extractors.raw_context_json_path))
    if not raw_context:
        warnings.append("RAW_CONTEXT_MISSING")
    return ExtractedResponse(
        answer_text=answer_text,
        citations=citations_list,
        citation_doc_ids=citation_doc_ids,
        citation_titles=citation_titles,
        citation_snippets=citation_snippets,
        metadata_values=metadata_values,
        raw_context=raw_context,
        warnings=_unique(warnings),
    )


def json_path(payload: Any, path: str) -> list[Any]:
    if not path or not path.startswith("$."):
        return []
    tokens = _parse_path(path[2:])
    current = [payload]
    for token in tokens:
        next_values: list[Any] = []
        for item in current:
            if token == "*":
                if isinstance(item, list):
                    next_values.extend(item)
            elif isinstance(token, int):
                if isinstance(item, list) and 0 <= token < len(item):
                    next_values.append(item[token])
            else:
                if isinstance(item, dict) and token in item:
                    next_values.append(item[token])
        current = next_values
    return current


def _parse_path(path: str) -> list[str | int]:
    tokens: list[str | int] = []
    for part in path.split("."):
        while "[" in part:
            name, rest = part.split("[", 1)
            if name:
                tokens.append(name)
            index, part = rest.split("]", 1)
            tokens.append("*" if index == "*" else int(index))
            if part.startswith("."):
                part = part[1:]
        if part:
            tokens.append(part)
    return tokens


def _as_object_list(values: list[Any]) -> list[dict[str, Any]]:
    if len(values) == 1 and isinstance(values[0], list):
        values = values[0]
    return [item for item in values if isinstance(item, dict)]


def _extract_from_items(items: list[dict[str, Any]], path: str, warnings: list[str]) -> list[str]:
    field_path = path if path.startswith("$.") else "$." + path.lstrip("$.")
    values: list[str] = []
    for item in items:
        extracted = json_path(item, field_path)
        if not extracted:
            warnings.append("RESPONSE_EXTRACTOR_MISSING_FIELD")
        values.extend(_flatten_strings(extracted))
    return _unique(values)


def _flatten_strings(values: list[Any]) -> list[str]:
    flattened: list[str] = []
    for value in values:
        if isinstance(value, dict):
            flattened.extend(_flatten_strings(list(value.values())))
        elif isinstance(value, list):
            flattened.extend(_flatten_strings(value))
        elif value is not None:
            flattened.append(str(value))
    return flattened


def _string_join(values: list[Any]) -> str:
    return "\n".join(_flatten_strings(values))


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
