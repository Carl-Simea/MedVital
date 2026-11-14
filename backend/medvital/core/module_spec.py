"""Health-module contract and the registry that validates observations semantically."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from medvital.core.schema import HealthObservation, ModuleId
from medvital.core.summary import ModuleSummary


@dataclass(frozen=True)
class MetricDefinition:
    """What a metric is. ``non_negative`` is a physical-plausibility rule (e.g. a dose
    cannot be below zero) — it is *not* a clinical threshold."""

    metric: str
    module: ModuleId
    unit: str
    description: str
    non_negative: bool = False
    required_context: tuple[str, ...] = ()
    optional_context: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.metric.split(".", 1)[0] != self.module.value:
            raise ValueError(f"metric {self.metric!r} is not in namespace {self.module.value!r}")


SummarizeFn = Callable[[str, Sequence[HealthObservation]], ModuleSummary]


@dataclass(frozen=True)
class HealthModuleSpec:
    """Everything the platform needs to know about one health module."""

    module_id: ModuleId
    name: str
    description: str
    metrics: tuple[MetricDefinition, ...]
    summarize: SummarizeFn
    method_notes: str = ""  # pointer into docs/SCIENTIFIC_METHODOLOGY.md

    def __post_init__(self) -> None:
        for m in self.metrics:
            if m.module != self.module_id:
                raise ValueError(f"{m.metric} registered under wrong module {self.module_id}")


class ObservationRejected(ValueError):
    """Raised when an observation is structurally valid but semantically unacceptable."""


@dataclass
class ModuleRegistry:
    _modules: dict[ModuleId, HealthModuleSpec] = field(default_factory=dict)
    _metrics: dict[str, MetricDefinition] = field(default_factory=dict)

    def register(self, spec: HealthModuleSpec) -> None:
        if spec.module_id in self._modules:
            raise ValueError(f"module {spec.module_id} already registered")
        for m in spec.metrics:
            if m.metric in self._metrics:
                raise ValueError(f"metric {m.metric} already registered")
        self._modules[spec.module_id] = spec
        self._metrics.update({m.metric: m for m in spec.metrics})

    def modules(self) -> list[HealthModuleSpec]:
        return [self._modules[k] for k in sorted(self._modules, key=lambda m: m.value)]

    def get(self, module_id: ModuleId) -> HealthModuleSpec:
        return self._modules[module_id]

    def validate(self, obs: HealthObservation) -> None:
        """Semantic checks: known metric, canonical unit, physical bounds, required context."""
        definition = self._metrics.get(obs.metric)
        if definition is None:
            raise ObservationRejected(f"unknown metric {obs.metric!r}")
        if definition.module != obs.module:
            raise ObservationRejected(f"metric {obs.metric!r} belongs to {definition.module.value!r}")
        if obs.unit != definition.unit:
            raise ObservationRejected(
                f"unit {obs.unit!r} does not match canonical unit {definition.unit!r} for {obs.metric}"
            )
        if not math.isfinite(obs.value):
            raise ObservationRejected("value must be finite")
        if definition.non_negative and obs.value < 0:
            raise ObservationRejected(f"{obs.metric} cannot be negative")
        missing = [k for k in definition.required_context if k not in obs.context]
        if missing:
            raise ObservationRejected(f"{obs.metric} requires context keys: {', '.join(missing)}")
        allowed = set(definition.required_context) | set(definition.optional_context)
        unknown = sorted(set(obs.context) - allowed)
        if unknown:
            raise ObservationRejected(f"{obs.metric} does not accept context keys: {', '.join(unknown)}")
