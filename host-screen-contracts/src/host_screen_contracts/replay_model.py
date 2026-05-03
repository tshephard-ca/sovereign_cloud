from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ReplayStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expect_screen_hash: str
    inputs: dict[str, str] = Field(default_factory=dict)
    aid: str
    expect_next_screen_hash: str


class ReplayCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    transaction_id: str
    case_id: str
    case_kind: str = "happy_path"
    start_screen_hash: str
    steps: list[ReplayStep]
    expected_response: dict[str, str] = Field(default_factory=dict)


def replay_case_to_dict(case: ReplayCase) -> dict:
    return case.model_dump(mode="json", exclude_none=True)
