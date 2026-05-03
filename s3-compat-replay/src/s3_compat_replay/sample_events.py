from __future__ import annotations

from .models import NormalizedS3Event


def sample_by_shape(events: list[NormalizedS3Event], limit: int) -> list[NormalizedS3Event]:
    selected: dict[str, NormalizedS3Event] = {}
    for event in events:
        key = event.source_shape_hash or f"{event.event_name}:{event.event_id}"
        existing = selected.get(key)
        if existing is None:
            selected[key] = event
            continue
        if existing.error_code and not event.error_code:
            selected[key] = event
    return sorted(selected.values(), key=lambda e: (e.operation_family, e.event_name or "", e.source_shape_hash or ""))[:limit]
