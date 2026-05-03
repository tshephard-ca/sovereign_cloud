from __future__ import annotations

from pathlib import Path

from .config import load_yaml
from .models import QualificationPolicy


def default_policy() -> QualificationPolicy:
    return QualificationPolicy()


def load_policy(path: Path | None) -> QualificationPolicy:
    if path is None:
        return default_policy()
    return QualificationPolicy(**load_yaml(path))
