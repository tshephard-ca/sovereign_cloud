from __future__ import annotations

from .contract_model import TransactionContract
from .field_classification import find_field
from .field_map import FieldMap, FieldMapEntry, VolatileRegion
from .models import FieldRole
from .models import screen_ref_for_seq
from .screen_hash import compute_screen_hashes
from .trace_schema import ActionEvent, ScreenEvent, TraceEvent
from .redact import REDACTED


class ReplayMismatch(AssertionError):
    pass


class TraceReplayDriver:
    """Offline driver that walks a recorded trace only."""

    def __init__(self, events: list[TraceEvent], contract: TransactionContract, field_map: FieldMap | None = None):
        self.events = events
        self.contract = contract
        self.field_map = field_map or self._field_map_from_contract()
        self.hash_field_map = field_map or self._hash_field_map_from_contract()
        self.screen_indices = [index for index, event in enumerate(events) if isinstance(event, ScreenEvent)]
        self.action_indices = [index for index, event in enumerate(events) if isinstance(event, ActionEvent)]
        self.screen_position = 0
        self.action_position = 0

    def _field_map_from_contract(self) -> FieldMap:
        entries: list[FieldMapEntry] = []
        if self.contract.field_map_fields:
            entries.extend(FieldMapEntry(**entry) for entry in self.contract.field_map_fields)
        for field in self.contract.request_fields + self.contract.response_fields:
            if any(entry.screen_ref == field.screen_ref and entry.row == field.row and entry.col == field.col for entry in entries):
                continue
            role = field.role if field.role in {item.value for item in FieldRole} else None
            entries.append(
                FieldMapEntry(
                    screen_ref=field.screen_ref,
                    field_id=field.field_id,
                    row=field.row,
                    col=field.col,
                    length=field.length,
                    name=field.name,
                    role=role,
                    type=field.type if field.type in {"string", "integer", "number", "boolean", "date", "time", "datetime"} else "string",
                    required=field.required,
                    sensitive=field.sensitive,
                    description=field.description,
                )
            )
        volatile_regions = [VolatileRegion(**region) for region in self.contract.volatile_regions]
        return FieldMap(
            transaction_id=self.contract.transaction_id,
            display_name=self.contract.display_name,
            endpoint_path=self.contract.endpoint_path,
            volatile_regions=volatile_regions,
            fields=entries,
        )

    def _hash_field_map_from_contract(self) -> FieldMap:
        volatile_regions = [VolatileRegion(**region) for region in self.contract.volatile_regions]
        return FieldMap(
            transaction_id=self.contract.transaction_id,
            display_name=self.contract.display_name,
            endpoint_path=self.contract.endpoint_path,
            volatile_regions=volatile_regions,
            fields=[FieldMapEntry(**entry) for entry in self.contract.field_map_fields],
        )

    @property
    def current_screen(self) -> ScreenEvent:
        if not self.screen_indices:
            raise ReplayMismatch("trace has no screens")
        return self.events[self.screen_indices[self.screen_position]]  # type: ignore[return-value]

    @property
    def current_screen_ref(self) -> str:
        return screen_ref_for_seq(self.current_screen.seq)

    def current_screen_hash(self) -> str:
        return compute_screen_hashes(self.current_screen, self.current_screen_ref, self.hash_field_map).screen_hash

    def apply(self, aid: str, inputs: dict[str, str]) -> str:
        if self.action_position >= len(self.action_indices):
            raise ReplayMismatch("no recorded action remains")
        action_index = self.action_indices[self.action_position]
        action = self.events[action_index]
        if not isinstance(action, ActionEvent):
            raise ReplayMismatch("internal replay position mismatch")
        if action.aid != aid.upper():
            raise ReplayMismatch(f"expected aid {action.aid}, got {aid}")

        contract_fields = {field.name: field for field in self.contract.request_fields}
        for name, value in inputs.items():
            field = contract_fields.get(name)
            if field is None:
                raise ReplayMismatch(f"unexpected input field {name}")
            matching_action_input = None
            for action_input in action.inputs:
                if action_input.field_id and action_input.field_id == field.field_id:
                    matching_action_input = action_input
                    break
                if action_input.row == field.row and action_input.col == field.col:
                    matching_action_input = action_input
                    break
            if matching_action_input is None:
                raise ReplayMismatch(f"input field {name} was not recorded for this step")
            if value != REDACTED and matching_action_input.value != value:
                raise ReplayMismatch(f"input value mismatch for {name}")

        next_screen_index = None
        for index in self.screen_indices:
            if index > action_index:
                next_screen_index = index
                break
        if next_screen_index is None:
            raise ReplayMismatch("recorded action has no following screen")
        self.screen_position = self.screen_indices.index(next_screen_index)
        self.action_position += 1
        return self.current_screen_hash()

    def extract_response(self) -> dict[str, str]:
        values: dict[str, str] = {}
        screens = {
            screen_ref_for_seq(event.seq): event for event in self.events if isinstance(event, ScreenEvent)
        }
        for field in self.contract.response_fields:
            screen = screens.get(field.screen_ref)
            if not screen:
                values.setdefault(field.name, "")
                continue
            trace_field = find_field(field.screen_ref, screen, self.field_map, field_id=field.field_id, row=field.row, col=field.col)
            value = trace_field.value if trace_field else ""
            if value or field.name not in values:
                values[field.name] = value
        return values

    def assert_no_unexpected_transition(self) -> None:
        if self.action_position != len(self.action_indices):
            raise ReplayMismatch("recorded trace has unapplied actions")
