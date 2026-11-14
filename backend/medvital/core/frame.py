"""Turn observation lists into per-series pandas frames, never mixing data origins.

A *series* is every observation sharing (metric, unit, data_origin, selected context
keys). Simulated, measured and modeled values therefore always land in separate series.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import pandas as pd

from medvital.core.schema import DataOrigin, HealthObservation

UNSPECIFIED = "unspecified"


@dataclass(frozen=True)
class SeriesGroup:
    metric: str
    unit: str
    data_origin: DataOrigin
    context: dict[str, str]
    # Columns: observed_at (UTC datetime64), value (float), id (str), days (float, since first obs).
    frame: pd.DataFrame


def group_series(
    observations: Iterable[HealthObservation],
    metric: str,
    context_keys: Sequence[str] = (),
) -> list[SeriesGroup]:
    """Group the observations of ``metric`` into time-ordered series."""
    rows = [
        {
            "id": str(o.id),
            "observed_at": o.observed_at,
            "value": o.value,
            "unit": o.unit,
            "data_origin": o.provenance.data_origin.value,
            **{f"ctx_{k}": o.context.get(k, UNSPECIFIED) for k in context_keys},
        }
        for o in observations
        if o.metric == metric
    ]
    if not rows:
        return []
    df = pd.DataFrame(rows)
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
    keys = ["data_origin", "unit", *[f"ctx_{k}" for k in context_keys]]
    groups: list[SeriesGroup] = []
    for key_values, part in df.groupby(keys, sort=True):
        key_tuple = key_values if isinstance(key_values, tuple) else (key_values,)
        origin, unit, *ctx_values = key_tuple
        frame = part.sort_values(["observed_at", "id"], kind="stable").reset_index(drop=True)
        frame["days"] = (frame["observed_at"] - frame["observed_at"].iloc[0]).dt.total_seconds() / 86400.0
        groups.append(
            SeriesGroup(
                metric=metric,
                unit=str(unit),
                data_origin=DataOrigin(origin),
                context=dict(zip(context_keys, map(str, ctx_values), strict=True)),
                frame=frame[["observed_at", "value", "id", "days"]],
            )
        )
    return groups
