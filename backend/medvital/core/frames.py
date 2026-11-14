"""Conversion of observations into pandas DataFrames for analysis."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd

from medvital.core.observation import HealthObservation

COLUMNS = ["id", "astronaut_id", "module", "metric", "value", "unit", "observed_at", "origin"]


def observations_to_frame(observations: Sequence[HealthObservation]) -> pd.DataFrame:
    rows = [
        {
            "id": str(o.id),
            "astronaut_id": o.astronaut_id,
            "module": o.module.value,
            "metric": o.metric,
            "value": o.value,
            "unit": o.unit,
            "observed_at": o.observed_at,
            "origin": o.provenance.origin.value,
        }
        for o in observations
    ]
    frame = pd.DataFrame(rows, columns=COLUMNS)
    if frame.empty:
        return frame
    frame["observed_at"] = pd.to_datetime(frame["observed_at"], utc=True)
    return frame.sort_values(["observed_at", "id"]).reset_index(drop=True)
