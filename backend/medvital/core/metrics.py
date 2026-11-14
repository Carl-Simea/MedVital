"""Metric specifications shared by all health modules."""

from __future__ import annotations

from dataclasses import dataclass

from medvital.core.provenance import DataOrigin

# Base metrics may be simulated or measured. Derived metrics exist only as modeled values.
BASE_ORIGINS = frozenset({DataOrigin.SIMULATED, DataOrigin.MEASURED})
DERIVED_ORIGINS = frozenset({DataOrigin.MODELED})


@dataclass(frozen=True)
class MetricSpec:
    """Declares one metric a health module understands.

    ``physical_min`` / ``physical_max`` are measurement-scale bounds (for example a value cannot
    be negative, or a 0-10 score cannot exceed 10). They are NOT clinical thresholds and are
    used only to keep simulated values on a valid scale.
    """

    name: str
    unit: str
    description: str
    allowed_origins: frozenset[DataOrigin] = BASE_ORIGINS
    physical_min: float | None = None
    physical_max: float | None = None
    # Spacing of simulated samples in days. Illustrative only.
    sim_cadence_days: int = 1

    @property
    def is_derived(self) -> bool:
        return self.allowed_origins == DERIVED_ORIGINS
