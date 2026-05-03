from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .models import Confidence


class ScreenFieldContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    role: str
    type: str = "string"
    screen_ref: str
    field_id: str | None = None
    row: int
    col: int
    length: int
    confidence: Confidence
    inference_source: str
    required: bool | None = None
    sensitive: bool | None = None
    pattern: str | None = None
    format: str | None = None
    description: str | None = None


class ScreenContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    screen_ref: str
    screen_hash: str
    normalized_text_hash: str
    field_layout_hash: str
    cursor_hash: str | None = None
    title: str | None = None
    rows: int
    cols: int
    fields: list[ScreenFieldContract] = Field(default_factory=list)
    function_keys: list[str] = Field(default_factory=list)
    subfile_regions: list[dict] = Field(default_factory=list)


class TransitionContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_screen_ref: str
    aid: str
    action_aid: str | None = None
    input_values: dict[str, str] = Field(default_factory=dict)
    to_screen_ref: str
    expected_to_screen_hash: str


class ReplayCaseSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    start_screen_hash: str
    case_kind: str = "happy_path"


class TransactionContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    transaction_id: str
    display_name: str
    endpoint_path: str
    confidence: Confidence
    screens: list[ScreenContract]
    transitions: list[TransitionContract]
    request_fields: list[ScreenFieldContract]
    response_fields: list[ScreenFieldContract]
    replay_cases: list[ReplayCaseSummary] = Field(default_factory=list)
    flow_graph: dict = Field(default_factory=dict)
    volatile_regions: list[dict] = Field(default_factory=list)
    field_map_fields: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


def contract_to_dict(contract: TransactionContract) -> dict:
    return contract.model_dump(mode="json", exclude_none=True)
