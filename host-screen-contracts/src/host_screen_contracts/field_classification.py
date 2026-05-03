from __future__ import annotations

import re
from collections.abc import Iterable

from .config import ExtractionConfig, DEFAULT_CONFIG
from .contract_model import ScreenFieldContract
from .field_map import FieldMap, FieldMapEntry
from .label_inference import infer_label, is_function_key_footer
from .models import Confidence, FieldRole, FieldType, WarningCode, generated_field_id
from .trace_schema import ActionInput, ScreenEvent, TraceField


ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def text_span(screen: ScreenEvent, row: int, col: int, length: int) -> str:
    if row < 1 or row > len(screen.text):
        return ""
    line = screen.text[row - 1]
    start = max(0, col - 1)
    return line.ljust(start + length)[start : start + length]


def _entry_value_from_text(screen: ScreenEvent, entry: FieldMapEntry) -> str:
    if entry.row is None or entry.col is None or entry.length is None:
        return ""
    raw = text_span(screen, entry.row, entry.col, entry.length)
    value = raw.strip()
    if value and set(value) <= {"_"}:
        return ""
    return value


def fields_for_screen(screen_ref: str, screen: ScreenEvent, field_map: FieldMap) -> list[TraceField]:
    fields = list(screen.fields)
    known = {(field.id, field.row, field.col) for field in fields}
    for entry in field_map.entries_for(screen_ref):
        if entry.row is None or entry.col is None or entry.length is None:
            continue
        field_id = entry.field_id or generated_field_id(entry.row, entry.col)
        key = (field_id, entry.row, entry.col)
        if key in known:
            continue
        role = entry.role or FieldRole.OUTPUT
        fields.append(
            TraceField(
                id=field_id,
                row=entry.row,
                col=entry.col,
                length=entry.length,
                value=_entry_value_from_text(screen, entry),
                protected=role not in (FieldRole.INPUT, FieldRole.INPUT_OUTPUT),
                display_only=role == FieldRole.OUTPUT,
                hidden=role == FieldRole.HIDDEN,
                attributes=[],
            )
        )
    return sorted(fields, key=lambda field: (field.row, field.col, field.id or ""))


def find_field(
    screen_ref: str,
    screen: ScreenEvent,
    field_map: FieldMap,
    *,
    field_id: str | None = None,
    row: int | None = None,
    col: int | None = None,
    fallback_value: str = "",
) -> TraceField | None:
    for field in fields_for_screen(screen_ref, screen, field_map):
        if field_id and field.id == field_id:
            return field
        if row is not None and col is not None and field.row == row and field.col == col:
            return field
    if row is not None and col is not None:
        entry = field_map.find_by_reference(screen_ref, field_id=field_id, row=row, col=col)
        return TraceField(
            id=field_id or generated_field_id(row, col),
            row=row,
            col=col,
            length=entry.length if entry and entry.length else max(len(fallback_value), 1),
            value=fallback_value,
            protected=False,
            display_only=False,
            hidden=False,
            attributes=[],
        )
    return None


def infer_type(values: Iterable[str], entry: FieldMapEntry | None = None) -> tuple[str, str | None, str | None, str]:
    if entry and entry.type:
        value = entry.type.value
        if entry.type == FieldType.DATE:
            return "string", "date", None, "field_map"
        if entry.type == FieldType.TIME:
            return "string", "time", None, "field_map"
        if entry.type == FieldType.DATETIME:
            return "string", "date-time", None, "field_map"
        return value, None, None, "field_map"

    observed = [value for value in values if value not in ("", None)]
    if observed and all(ISO_DATE_RE.match(value.strip()) for value in observed):
        return "string", "date", None, "observed_value"
    if observed and all(value.strip().isdigit() for value in observed):
        return "string", None, "^[0-9]+$", "observed_value"
    return "string", None, None, "observed_value"


def contract_field_from_trace_field(
    screen_ref: str,
    screen: ScreenEvent,
    field: TraceField,
    role: FieldRole,
    field_map: FieldMap,
    *,
    required_default: bool | None,
    observed_values: list[str] | None = None,
    config: ExtractionConfig = DEFAULT_CONFIG,
) -> ScreenFieldContract:
    entry = field_map.find_for_field(screen_ref, field) or field_map.find_by_reference(
        screen_ref, field_id=field.id, row=field.row, col=field.col
    )
    if entry and entry.name:
        name = entry.name
        confidence = Confidence.HIGH
        inference_source = "field_map"
    else:
        inferred = infer_label(screen, field, config)
        name = inferred.name
        confidence = inferred.confidence
        inference_source = inferred.source

    field_type, field_format, pattern, type_source = infer_type(observed_values or [field.value], entry)
    if entry and entry.role:
        role = entry.role
    return ScreenFieldContract(
        name=name,
        role=role.value,
        type=field_type,
        screen_ref=screen_ref,
        field_id=field.id,
        row=field.row,
        col=field.col,
        length=field.length,
        confidence=confidence,
        inference_source=inference_source if type_source != "field_map" else "field_map",
        required=entry.required if entry and entry.required is not None else required_default,
        sensitive=entry.sensitive if entry else None,
        pattern=pattern,
        format=field_format,
        description=entry.description if entry else None,
    )


def request_fields_from_actions(
    action_pairs: list[tuple[str, ScreenEvent, list[ActionInput]]],
    field_map: FieldMap,
    config: ExtractionConfig = DEFAULT_CONFIG,
) -> tuple[list[ScreenFieldContract], list[str]]:
    warnings: list[str] = []
    results: list[ScreenFieldContract] = []
    seen: set[tuple[str, str | None, int, int]] = set()
    for screen_ref, screen, inputs in action_pairs:
        for action_input in inputs:
            field = find_field(
                screen_ref,
                screen,
                field_map,
                field_id=action_input.field_id,
                row=action_input.row,
                col=action_input.col,
                fallback_value=action_input.value,
            )
            if field is None:
                continue
            key = (screen_ref, field.id, field.row, field.col)
            if key in seen:
                continue
            seen.add(key)
            contract_field = contract_field_from_trace_field(
                screen_ref,
                screen,
                field,
                FieldRole.INPUT,
                field_map,
                required_default=True,
                observed_values=[action_input.value],
                config=config,
            )
            if contract_field.confidence == Confidence.MEDIUM:
                warnings.append(WarningCode.FIELD_NAMES_INFERRED.value)
            if contract_field.confidence == Confidence.LOW:
                warnings.append(WarningCode.GENERATED_COORDINATE_NAMES.value)
            results.append(contract_field)
    return results, warnings


def response_fields_from_screens(
    screens: list[tuple[str, ScreenEvent]],
    field_map: FieldMap,
    config: ExtractionConfig = DEFAULT_CONFIG,
) -> tuple[list[ScreenFieldContract], list[str]]:
    warnings: list[str] = []
    if not screens:
        return [], warnings

    screen_by_ref = dict(screens)
    mapped_outputs: list[ScreenFieldContract] = []
    for entry in field_map.fields:
        if entry.role not in (FieldRole.OUTPUT, FieldRole.INPUT_OUTPUT, FieldRole.ERROR_MESSAGE):
            continue
        target_refs = [entry.screen_ref] if entry.screen_ref != "*" else [screens[-1][0]]
        for screen_ref in target_refs:
            screen = screen_by_ref.get(screen_ref)
            if not screen:
                continue
            field = None
            if entry.field_id or (entry.row is not None and entry.col is not None):
                field = find_field(
                    screen_ref,
                    screen,
                    field_map,
                    field_id=entry.field_id,
                    row=entry.row,
                    col=entry.col,
                )
            if field is None:
                continue
            mapped_outputs.append(
                contract_field_from_trace_field(
                    screen_ref,
                    screen,
                    field,
                    entry.role,
                    field_map,
                    required_default=False,
                    observed_values=[field.value],
                    config=config,
                )
            )
    if mapped_outputs:
        return _dedupe_fields(mapped_outputs), warnings

    final_ref, final_screen = screens[-1]
    for field in fields_for_screen(final_ref, final_screen, field_map):
        if field.hidden or not (field.protected or field.display_only) or not field.value.strip():
            continue
        if is_function_key_footer(final_screen.text[field.row - 1] if field.row - 1 < len(final_screen.text) else ""):
            continue
        contract_field = contract_field_from_trace_field(
            final_ref,
            final_screen,
            field,
            FieldRole.OUTPUT,
            field_map,
            required_default=False,
            observed_values=[field.value],
            config=config,
        )
        if contract_field.confidence == Confidence.LOW:
            warnings.append(WarningCode.GENERATED_COORDINATE_NAMES.value)
        else:
            warnings.append(WarningCode.FIELD_NAMES_INFERRED.value)
        if len(mapped_outputs) < config.max_response_fields_without_field_map:
            mapped_outputs.append(contract_field)
    if mapped_outputs:
        warnings.append(WarningCode.OUTPUT_FIELD_SELECTION_REQUIRES_REVIEW.value)
    return _dedupe_fields(mapped_outputs), warnings


def _dedupe_fields(fields: list[ScreenFieldContract]) -> list[ScreenFieldContract]:
    result: list[ScreenFieldContract] = []
    seen: set[tuple[str, str | None, int, int, str]] = set()
    for field in fields:
        key = (field.screen_ref, field.field_id, field.row, field.col, field.name)
        if key not in seen:
            seen.add(key)
            result.append(field)
    return result


def detect_subfile_like(screen: ScreenEvent, config: ExtractionConfig = DEFAULT_CONFIG) -> bool:
    text = "\n".join(screen.text).upper()
    if any(token in text for token in ("PAGEUP", "PAGEDOWN", "MORE", "BOTTOM", "OPT", "OPTION")):
        return True
    patterns: dict[str, int] = {}
    for row in screen.text:
        stripped = row.rstrip()
        if not stripped:
            continue
        pattern = re.sub(r"[A-Za-z0-9]+", "X", stripped)
        pattern = re.sub(r"\s+", " ", pattern).strip()
        patterns[pattern] = patterns.get(pattern, 0) + 1
    return any(count >= config.detect_subfile_min_repeated_rows for count in patterns.values())


def detect_error_screen(screen: ScreenEvent) -> bool:
    text = "\n".join(screen.text).lower()
    return any(
        token in text
        for token in (
            "error",
            "invalid",
            "not found",
            "required",
            "press reset",
            "permission denied",
            "denied",
            "not authorized",
            "unauthorized",
            "unsupported",
        )
    )
