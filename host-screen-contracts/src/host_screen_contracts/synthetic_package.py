from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


PACKAGE_DIRS = ("traces", "field_maps", "cases", "expected", "review", "privacy", "provenance")


@dataclass(frozen=True)
class SyntheticCaseSpec:
    case_id: str
    trace: str
    purpose: str
    case_kind: str
    description: str = ""

    def manifest_value(self) -> dict[str, str]:
        value = {
            "trace": self.trace,
            "purpose": self.purpose,
            "case_kind": self.case_kind,
        }
        if self.description:
            value["description"] = self.description
        return value


@dataclass(frozen=True)
class SyntheticPackageSpec:
    package_id: str
    transaction_id: str
    maturity_level: str
    evidence_kind: str
    actual_maturity_level: str
    simulates_maturity_level: str
    description: str
    tags: list[str]
    field_map: str | None = "field_maps/transaction.fields.yml"
    business_process: str = ""
    operator_goal: str = ""
    screen_family: str = "5250-style screen"
    data_origin: str = "deterministic synthetic trace generated offline"
    value_strategy: str = "representative fake fixed-width values"
    known_limitations: list[str] = field(default_factory=list)


class SyntheticPackageBuilder:
    def __init__(self, root: str | Path, spec: SyntheticPackageSpec, *, scenario: str) -> None:
        self.root = Path(root)
        self.spec = spec
        self.scenario = scenario
        self.package = self.root / spec.package_id
        self.create_directories()

    def create_directories(self) -> None:
        for child in PACKAGE_DIRS:
            (self.package / child).mkdir(parents=True, exist_ok=True)

    def write_provenance(self) -> None:
        self.write_yaml(
            "provenance/generation.yml",
            {
                "schema_version": "1.0",
                "generated_by": "host-screen-contracts",
                "data_kind": "deterministic_synthetic",
                "scenario": self.scenario,
                "contains_customer_data": False,
                "contains_live_host_capture": False,
                "network_access_used": False,
            },
        )

    def write_manifest(self, cases: list[SyntheticCaseSpec], *, replay_cases: dict[str, str] | None = None) -> None:
        manifest = {
            "schema_version": "1.0",
            "package_id": self.spec.package_id,
            "transaction_id": self.spec.transaction_id,
            "maturity_level": self.spec.maturity_level,
            "evidence_kind": self.spec.evidence_kind,
            "actual_maturity_level": self.spec.actual_maturity_level,
            "simulates_maturity_level": self.spec.simulates_maturity_level,
            "description": self.spec.description,
            "business_process": self.spec.business_process,
            "operator_goal": self.spec.operator_goal,
            "screen_family": self.spec.screen_family,
            "data_origin": self.spec.data_origin,
            "value_strategy": self.spec.value_strategy,
            "known_limitations": self.spec.known_limitations,
            "traces": {case.case_id: case.trace for case in cases},
            "cases": {case.case_id: case.manifest_value() for case in cases},
            "field_map": self.spec.field_map,
            "replay_cases": replay_cases or {},
            "tags": self.spec.tags,
        }
        self.write_yaml("manifest.yml", manifest)

    def write_field_map(
        self,
        *,
        display_name: str,
        endpoint_path: str,
        fields: list[dict[str, Any]],
        volatile_regions: list[dict[str, Any]] | None = None,
    ) -> None:
        self.write_yaml(
            self.spec.field_map or "field_maps/transaction.fields.yml",
            {
                "transaction_id": self.spec.transaction_id,
                "display_name": display_name,
                "endpoint_path": endpoint_path,
                **({"volatile_regions": volatile_regions} if volatile_regions else {}),
                "fields": fields,
            },
        )

    def write_trace(self, case_id: str, events: list[dict[str, Any]]) -> None:
        self.write_jsonl(f"traces/{case_id}.trace.jsonl", events)

    def write_jsonl(self, relative_path: str, events: list[dict[str, Any]]) -> None:
        path = self.package / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(event, separators=(",", ":")) for event in events) + "\n")

    def write_yaml(self, relative_path: str, data: dict[str, Any]) -> None:
        path = self.package / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, sort_keys=False))


def case_spec(case_id: str, *, purpose: str, case_kind: str, description: str = "") -> SyntheticCaseSpec:
    return SyntheticCaseSpec(
        case_id=case_id,
        trace=f"traces/{case_id}.trace.jsonl",
        purpose=purpose,
        case_kind=case_kind,
        description=description,
    )
