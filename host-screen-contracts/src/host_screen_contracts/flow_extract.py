from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ExtractionConfig, DEFAULT_CONFIG
from .contract_model import (
    ReplayCaseSummary,
    ScreenContract,
    ScreenFieldContract,
    TransactionContract,
    TransitionContract,
)
from .field_classification import (
    detect_error_screen,
    detect_subfile_like,
    find_field,
    request_fields_from_actions,
    response_fields_from_screens,
)
from .field_map import FieldMap
from .flow_graph import build_flow_graph
from .label_inference import detect_function_keys, infer_screen_title, is_function_key_footer
from .models import BlockerCode, Confidence, WarningCode, screen_ref_for_seq
from .redact import REDACTED, redact_value
from .replay_model import ReplayCase, ReplayStep
from .screen_hash import compute_screen_hashes
from .subfile_analysis import analyze_subfile_regions
from .trace_schema import ActionEvent, ScreenEvent, TraceEvent
from .validate_trace import validate_trace


@dataclass(frozen=True)
class ExtractionResult:
    contract: TransactionContract
    replay_case: ReplayCase
    summary: dict[str, Any]


def _default_display_name(transaction_id: str) -> str:
    return transaction_id.replace("_", " ").replace("-", " ").title()


def _default_endpoint_path(transaction_id: str) -> str:
    return f"/transactions/{transaction_id.replace('_', '-')}"


def _screen_ref_pairs(events: list[TraceEvent]) -> list[tuple[str, ScreenEvent]]:
    return [(screen_ref_for_seq(event.seq), event) for event in events if isinstance(event, ScreenEvent)]


def _previous_screen(events: list[TraceEvent], index: int) -> tuple[str, ScreenEvent] | None:
    for event in reversed(events[:index]):
        if isinstance(event, ScreenEvent):
            return screen_ref_for_seq(event.seq), event
    return None


def _next_screen(events: list[TraceEvent], index: int) -> tuple[str, ScreenEvent] | None:
    for event in events[index + 1 :]:
        if isinstance(event, ScreenEvent):
            return screen_ref_for_seq(event.seq), event
        if isinstance(event, ActionEvent):
            return None
    return None


def _field_value(screen_ref: str, screen: ScreenEvent, field: ScreenFieldContract, field_map: FieldMap) -> str:
    trace_field = find_field(screen_ref, screen, field_map, field_id=field.field_id, row=field.row, col=field.col)
    return trace_field.value if trace_field else ""


def _confidence(
    warnings: list[str],
    blockers: list[str],
    request_fields: list[ScreenFieldContract],
    response_fields: list[ScreenFieldContract],
    plain_text_only: bool,
) -> Confidence:
    if blockers:
        return Confidence.LOW
    if plain_text_only:
        return Confidence.LOW
    if any(field.confidence == Confidence.LOW for field in request_fields + response_fields):
        return Confidence.LOW
    if warnings:
        return Confidence.MEDIUM
    if any(field.confidence == Confidence.MEDIUM for field in request_fields + response_fields):
        return Confidence.MEDIUM
    return Confidence.HIGH


def _summary_counts(fields: list[ScreenFieldContract]) -> tuple[int, int, int]:
    coordinate = sum(1 for field in fields if field.inference_source == "coordinate")
    label = sum(1 for field in fields if field.inference_source == "label")
    mapped = sum(1 for field in fields if field.inference_source == "field_map")
    return coordinate, label, mapped


def _redact_action_value(value: str, field: ScreenFieldContract, entry: Any, redact: bool) -> str:
    if redact and not (entry and entry.sensitive is False):
        return REDACTED
    return value


def extract_transaction(
    events: list[TraceEvent],
    *,
    transaction_id: str,
    case_id: str | None = None,
    case_kind: str = "happy_path",
    field_map: FieldMap | None = None,
    strict: bool = False,
    redact: bool = False,
    screen_size: tuple[int, int] | None = None,
    openapi_path: str | None = None,
    config: ExtractionConfig = DEFAULT_CONFIG,
    output_paths: dict[str, str] | None = None,
) -> ExtractionResult:
    field_map = field_map or FieldMap()
    validation = validate_trace(events, strict=strict, screen_size=screen_size, field_map=field_map)
    warnings = list(validation.warnings)
    blockers = list(validation.blockers)

    screen_pairs = _screen_ref_pairs(events)
    screen_hashes = {
        screen_ref: compute_screen_hashes(screen, screen_ref, field_map, config)
        for screen_ref, screen in screen_pairs
    }
    repeated_hashes = {
        hashes.screen_hash
        for hashes in screen_hashes.values()
        if list(hash.screen_hash for hash in screen_hashes.values()).count(hashes.screen_hash) > 1
    }
    if repeated_hashes:
        warnings.append(WarningCode.REPEATED_SCREEN_HASH.value)

    plain_text_only = bool(screen_pairs) and all(not screen.fields for _, screen in screen_pairs)
    if plain_text_only:
        warnings.append(WarningCode.PLAIN_TEXT_ONLY_TRACE.value)

    action_pairs = []
    transitions: list[TransitionContract] = []
    replay_steps: list[ReplayStep] = []
    request_value_lookup: dict[tuple[str, str | None, int | None, int | None], str] = {}
    for index, event in enumerate(events):
        if not isinstance(event, ActionEvent):
            continue
        previous = _previous_screen(events, index)
        next_screen = _next_screen(events, index)
        if not previous or not next_screen:
            continue
        from_ref, from_screen = previous
        to_ref, _to_screen = next_screen
        action_pairs.append((from_ref, from_screen, event.inputs))
        for action_input in event.inputs:
            request_value_lookup[(from_ref, action_input.field_id, action_input.row, action_input.col)] = action_input.value
        transitions.append(
            TransitionContract(
                from_screen_ref=from_ref,
                aid=event.aid,
                action_aid=event.aid,
                input_values={},
                to_screen_ref=to_ref,
                expected_to_screen_hash=screen_hashes[to_ref].screen_hash,
            )
        )
        replay_steps.append(
            ReplayStep(
                expect_screen_hash=screen_hashes[from_ref].screen_hash,
                inputs={},
                aid=event.aid,
                expect_next_screen_hash=screen_hashes[to_ref].screen_hash,
            )
        )

    request_fields, request_warnings = request_fields_from_actions(action_pairs, field_map, config)
    response_fields, response_warnings = response_fields_from_screens(screen_pairs, field_map, config)
    warnings.extend(request_warnings)
    warnings.extend(response_warnings)

    if not request_fields:
        blockers.append(BlockerCode.NO_INPUT_FIELDS.value)
    if not response_fields:
        blockers.append(BlockerCode.NO_FINAL_OUTPUT_FIELDS.value)

    if strict and any(field.inference_source == "coordinate" for field in request_fields + response_fields):
        blockers.append(BlockerCode.GENERATED_COORDINATE_NAMES_IN_STRICT_MODE.value)

    for screen_ref, screen in screen_pairs:
        if detect_subfile_like(screen, config):
            warnings.append(WarningCode.SUBFILE_LIKE_REGION_DETECTED.value)
        if detect_error_screen(screen):
            warnings.append(WarningCode.ERROR_SCREEN_RECORDED.value)
        nonblank_rows = [row for row in screen.text if row.strip()]
        if nonblank_rows and all(is_function_key_footer(row) for row in nonblank_rows):
            warnings.append(WarningCode.FUNCTION_KEY_ONLY_SCREEN.value)

    request_field_by_screen_coord = {
        (field.screen_ref, field.field_id, field.row, field.col): field for field in request_fields
    }
    for transition, replay_step, (from_ref, _screen, inputs) in zip(transitions, replay_steps, action_pairs, strict=False):
        named_inputs: dict[str, str] = {}
        for action_input in inputs:
            matching = None
            for field in request_fields:
                if field.screen_ref != from_ref:
                    continue
                if action_input.field_id and field.field_id == action_input.field_id:
                    matching = field
                    break
                if action_input.row == field.row and action_input.col == field.col:
                    matching = field
                    break
            if matching:
                entry = field_map.find_by_reference(
                    from_ref,
                    field_id=matching.field_id,
                    row=matching.row,
                    col=matching.col,
                )
                named_inputs[matching.name] = _redact_action_value(action_input.value, matching, entry, redact)
        transition.input_values.update(named_inputs)
        replay_step.inputs.update(named_inputs)

    field_roles_by_screen: dict[str, list[ScreenFieldContract]] = {}
    for field in request_fields + response_fields:
        field_roles_by_screen.setdefault(field.screen_ref, []).append(field)

    screens: list[ScreenContract] = []
    for screen_ref, screen in screen_pairs:
        hashes = screen_hashes[screen_ref]
        screens.append(
            ScreenContract(
                screen_ref=screen_ref,
                screen_hash=hashes.screen_hash,
                normalized_text_hash=hashes.normalized_text_hash,
                field_layout_hash=hashes.field_layout_hash,
                cursor_hash=hashes.cursor_hash,
                title=infer_screen_title(screen, field_map=field_map, screen_ref=screen_ref),
                rows=screen.rows,
                cols=screen.cols,
                fields=field_roles_by_screen.get(screen_ref, []),
                function_keys=detect_function_keys(screen),
                subfile_regions=analyze_subfile_regions(screen, config),
            )
        )

    final_ref, final_screen = screen_pairs[-1] if screen_pairs else ("", None)  # type: ignore[assignment]
    expected_response: dict[str, str] = {}
    if final_screen is not None:
        for field in response_fields:
            screen = dict(screen_pairs).get(field.screen_ref)
            if not screen:
                continue
            entry = field_map.find_by_reference(field.screen_ref, field_id=field.field_id, row=field.row, col=field.col)
            expected_response[field.name] = redact_value(
                _field_value(field.screen_ref, screen, field, field_map),
                field.name,
                entry,
                redact=redact,
            )

    start_hash = screens[0].screen_hash if screens else ""
    replay_case = ReplayCase(
        transaction_id=transaction_id,
        case_id=case_id or f"{case_kind}_{transaction_id}",
        case_kind=case_kind,
        start_screen_hash=start_hash,
        steps=replay_steps,
        expected_response=expected_response,
    )

    warnings = sorted(set(warnings), key=warnings.index)
    blockers = sorted(set(blockers), key=blockers.index)
    confidence = _confidence(warnings, blockers, request_fields, response_fields, plain_text_only)
    display_name = field_map.display_name or _default_display_name(transaction_id)
    endpoint_path = openapi_path or field_map.endpoint_path or _default_endpoint_path(transaction_id)

    contract = TransactionContract(
        transaction_id=transaction_id,
        display_name=display_name,
        endpoint_path=endpoint_path,
        confidence=confidence,
        screens=screens,
        transitions=transitions,
        request_fields=request_fields,
        response_fields=response_fields,
        replay_cases=[ReplayCaseSummary(case_id=replay_case.case_id, case_kind=case_kind, start_screen_hash=start_hash)],
        flow_graph={},
        volatile_regions=[region.model_dump(mode="json") for region in field_map.volatile_regions],
        field_map_fields=[entry.model_dump(mode="json", exclude_none=True) for entry in field_map.fields],
        warnings=warnings,
        blockers=blockers,
    )
    contract.flow_graph = build_flow_graph([(replay_case.case_id, case_kind, contract)])

    all_fields = request_fields + response_fields
    coordinate_count, label_count, mapped_count = _summary_counts(all_fields)
    summary = {
        "transaction_id": transaction_id,
        "fit_for_review": not blockers,
        "confidence": confidence.value,
        "screen_count": len(screens),
        "action_count": len([event for event in events if isinstance(event, ActionEvent)]),
        "request_field_count": len(request_fields),
        "response_field_count": len(response_fields),
        "generated_coordinate_names": coordinate_count,
        "inferred_label_names": label_count,
        "field_map_names": mapped_count,
        "warnings": warnings,
        "blockers": blockers,
        "outputs": output_paths or {},
    }
    return ExtractionResult(contract=contract, replay_case=replay_case, summary=summary)
