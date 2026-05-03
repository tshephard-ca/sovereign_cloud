from __future__ import annotations

from pathlib import Path

from .config import load_yaml
from .models import NodeInventory


def load_node_inventory(path: Path | None) -> NodeInventory | None:
    if path is None:
        return None
    return NodeInventory(**load_yaml(path))
