"""Composition root for health modules — the only place that imports all four."""

from __future__ import annotations

from medvital.core.module_spec import ModuleRegistry
from medvital.modules import behavioral, bone, cardiovascular, radiation


def build_registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    for module in (radiation, bone, cardiovascular, behavioral):
        registry.register(module.SPEC)
    return registry
