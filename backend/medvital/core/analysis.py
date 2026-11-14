"""Module-agnostic descriptive summaries.

Summaries are computed per (metric, origin): simulated, measured and modeled values are never
averaged together.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel

from medvital.core.frames import observations_to_frame
from medvital.core.metrics import MetricSpec
from medvital.core.observation import HealthObservation, ModuleId
from medvital.core.provenance import DataOrigin
from medvital.core.stats import series_stats

RESEARCH_NOTICE = (
    "Research prototype. Descriptive statistics only: not a medical device, not a diagnosis, "
    "and no clinical thresholds are applied."
)


class MetricSummary(BaseModel):
    metric: str
    unit: str
    origin: DataOrigin
    n: int
    first_observed_at: datetime
    last_observed_at: datetime
    latest_value: float
    mean: float
    std: float | None
    trend_per_day: float | None


class ModuleSummary(BaseModel):
    module: ModuleId
    astronaut_id: str
    n_observations: int
    metrics: list[MetricSummary]
    notice: str = RESEARCH_NOTICE


def summarize_module(
    module: ModuleId,
    astronaut_id: str,
    specs: Sequence[MetricSpec],
    observations: Sequence[HealthObservation],
) -> ModuleSummary:
    known = {s.name: s for s in specs}
    selected = [
        o
        for o in observations
        if o.module is module and o.astronaut_id == astronaut_id and o.metric in known
    ]
    frame = observations_to_frame(selected)
    metrics: list[MetricSummary] = []
    if not frame.empty:
        for (metric, origin), group in frame.groupby(["metric", "origin"], sort=True):
            times = [t.to_pydatetime() for t in group["observed_at"]]
            values = group["value"].tolist()
            st = series_stats(times, values)
            metrics.append(
                MetricSummary(
                    metric=str(metric),
                    unit=known[str(metric)].unit,
                    origin=DataOrigin(str(origin)),
                    n=st.n,
                    first_observed_at=times[0],
                    last_observed_at=times[-1],
                    latest_value=values[-1],
                    mean=st.mean,
                    std=st.std,
                    trend_per_day=st.slope_per_day,
                )
            )
    return ModuleSummary(
        module=module,
        astronaut_id=astronaut_id,
        n_observations=len(selected),
        metrics=metrics,
    )
