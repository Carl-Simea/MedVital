"""Module summary contract: descriptive statistics + clearly-labelled derived values.

Summaries are *descriptive*. They never classify a subject as healthy/unhealthy, never
compare against clinical thresholds, and never diagnose. ``NOTICE`` travels with every
summary so any client rendering one can show it.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from medvital.core.frame import group_series
from medvital.core.schema import DataOrigin, HealthObservation, ModuleId
from medvital.core.stats import describe

NOTICE = (
    "Descriptive statistics and documented calculations only. Not a diagnosis, not medical "
    "advice, and no clinical thresholds are applied. Values keep their data origin "
    "(simulated / measured / modeled)."
)


class MetricSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric: str
    unit: str
    data_origin: DataOrigin
    context: dict[str, str] = Field(default_factory=dict)
    count: int
    first_observed_at: datetime
    last_observed_at: datetime
    mean: float
    std: float | None
    minimum: float
    maximum: float


class DerivedValue(BaseModel):
    """A value computed by a documented method. Always ``modeled`` by definition."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    value: float
    unit: str
    data_origin: Literal[DataOrigin.MODELED] = DataOrigin.MODELED
    method: str
    input_metric: str
    input_origin: DataOrigin
    input_count: int
    context: dict[str, str] = Field(default_factory=dict)


class ModuleSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    module: ModuleId
    subject_id: str
    observation_count: int
    metric_summaries: list[MetricSummary]
    derived_values: list[DerivedValue]
    warnings: list[str] = Field(default_factory=list)
    notice: str = NOTICE


def summarize_metric(
    observations: Sequence[HealthObservation],
    metric: str,
    context_keys: Sequence[str] = (),
) -> list[MetricSummary]:
    """Descriptive statistics per (origin, unit, context) series of ``metric``."""
    out: list[MetricSummary] = []
    for group in group_series(observations, metric, context_keys):
        s = describe(group.frame["value"].to_numpy())
        out.append(
            MetricSummary(
                metric=metric,
                unit=group.unit,
                data_origin=group.data_origin,
                context=group.context,
                count=s.count,
                first_observed_at=group.frame["observed_at"].iloc[0].to_pydatetime(),
                last_observed_at=group.frame["observed_at"].iloc[-1].to_pydatetime(),
                mean=s.mean,
                std=s.std,
                minimum=s.minimum,
                maximum=s.maximum,
            )
        )
    return out
