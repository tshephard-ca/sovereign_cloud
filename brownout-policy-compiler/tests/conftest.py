from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture()
def root() -> Path:
    return ROOT


@pytest.fixture()
def examples(root: Path) -> Path:
    return root / "examples"


@pytest.fixture()
def event_data(examples: Path) -> dict:
    return json.loads((examples / "events" / "ddos_event.json").read_text())


@pytest.fixture()
def service_data(examples: Path) -> dict:
    return yaml.safe_load((examples / "service_priority.yml").read_text())


def write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, indent=2, sort_keys=True))
    return path


def write_yaml(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


@pytest.fixture()
def mutable_event(event_data: dict) -> dict:
    return deepcopy(event_data)


@pytest.fixture()
def mutable_services(service_data: dict) -> dict:
    return deepcopy(service_data)


@pytest.fixture()
def compile_options_factory(tmp_path: Path, examples: Path):
    from brownout_policy_compiler.compile_rules import CompileOptions

    def factory(**overrides):
        values = {
            "event_path": examples / "events" / "ddos_event.json",
            "services_path": examples / "service_priority.yml",
            "output_plan": tmp_path / "brownout_plan.yml",
            "output_actions": tmp_path / "actions.csv",
            "output_rollback": tmp_path / "rollback_plan.yml",
            "summary": tmp_path / "summary.json",
            "incident_id": "INC-12345",
            "now": "2026-01-01T00:05:00Z",
        }
        values.update(overrides)
        return CompileOptions(**values)

    return factory

