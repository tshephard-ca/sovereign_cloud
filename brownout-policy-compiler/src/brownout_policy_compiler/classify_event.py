from __future__ import annotations

from .models import AttackClass, DdosEvent


def classify_attack_context(event: DdosEvent) -> str:
    if event.attack_class == AttackClass.VOLUMETRIC:
        return "volumetric"
    if event.attack_class == AttackClass.PROTOCOL:
        return "protocol"
    if event.attack_class == AttackClass.APPLICATION:
        return "application"
    if event.attack_class == AttackClass.MIXED:
        return "mixed"
    return "unknown"

