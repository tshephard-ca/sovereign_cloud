from __future__ import annotations

from typing import Any

from .field_classification import fields_for_screen, infer_type
from .field_map import FieldMap
from .label_inference import infer_label
from .models import FieldRole, screen_ref_for_seq
from .trace_schema import ScreenEvent, TraceEvent


def generate_label_sheet(
    events: list[TraceEvent],
    *,
    field_map: FieldMap | None = None,
    include_values: bool = False,
) -> dict[str, Any]:
    field_map = field_map or FieldMap()
    items: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, ScreenEvent):
            continue
        screen_ref = screen_ref_for_seq(event.seq)
        for field in fields_for_screen(screen_ref, event, field_map):
            entry = field_map.find_for_field(screen_ref, field)
            inferred = infer_label(event, field)
            proposed_name = entry.name if entry and entry.name else inferred.name
            role = entry.role.value if entry and entry.role else (
                FieldRole.HIDDEN.value if field.hidden else FieldRole.OUTPUT.value if field.protected or field.display_only else FieldRole.INPUT.value
            )
            field_type, field_format, pattern, source = infer_type([field.value], entry)
            item = {
                "screen_ref": screen_ref,
                "field_id": field.id,
                "row": field.row,
                "col": field.col,
                "length": field.length,
                "inferred_label": inferred.label,
                "proposed_name": proposed_name,
                "role": role,
                "type": field_type,
                "format": field_format,
                "pattern": pattern,
                "sensitive": entry.sensitive if entry and entry.sensitive is not None else False,
                "confidence": "HIGH" if entry and entry.name else inferred.confidence.value,
                "inference_source": "field_map" if entry and entry.name else inferred.source,
                "review_status": "needs_review" if not (entry and entry.name) else "accepted",
                "reviewer_notes": "",
                "type_source": source,
            }
            if include_values:
                item["observed_value_sample"] = field.value
            items.append(item)
    return {
        "schema_version": "1.0",
        "transaction_id": field_map.transaction_id,
        "field_count": len(items),
        "fields": items,
    }
