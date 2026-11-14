"""The HealthModule contract every health module implements.

A module is a small, self-contained bundle: its metric specs, a function that derives modeled
observations from base observations, and simulation context. Everything else (simulation,
summaries) is provided generically by core so the four modules stay uniform and independent.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from medvital.core.analysis import ModuleSummary, summarize_module
from medvital.core.metrics import MetricSpec
from medvital.core.observation import HealthObservation, ModuleId
from medvital.core.profiles import AstronautProfile
from medvital.core.simulation import simulate_observations

DeriveFn = Callable[[Sequence[HealthObservation]], list[HealthObservation]]


@dataclass(frozen=True)
class HealthModule:
    id: ModuleId
    title: str
    description: str
    metrics: tuple[MetricSpec, ...]
    # Computes MODELED observations from base (simulated or measured) observations.
    derive: DeriveFn
    sim_context: Mapping[str, str] = field(default_factory=dict)

    def spec(self, metric: str) -> MetricSpec | None:
        return next((m for m in self.metrics if m.name == metric), None)

    def simulate(
        self, profile: AstronautProfile, start: datetime, days: int, seed: int
    ) -> list[HealthObservation]:
        return simulate_observations(
            profile=profile,
            module=self.id,
            specs=self.metrics,
            context=self.sim_context,
            start=start,
            days=days,
            seed=seed,
        )

    def analyze(
        self, astronaut_id: str, observations: Sequence[HealthObservation]
    ) -> ModuleSummary:
        return summarize_module(self.id, astronaut_id, self.metrics, observations)
