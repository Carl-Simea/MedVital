"""Small, presentation-free statistical helpers shared by the health modules.

Nothing here knows about health, thresholds or interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats as sp_stats


@dataclass(frozen=True)
class DescriptiveStats:
    count: int
    mean: float
    std: float | None  # sample standard deviation (ddof=1); None when count < 2
    minimum: float
    maximum: float


@dataclass(frozen=True)
class TrendFit:
    """Ordinary least-squares line ``y = intercept + slope_per_day * days``."""

    slope_per_day: float
    intercept: float
    r_value: float
    slope_stderr: float
    count: int


def describe(values: np.ndarray) -> DescriptiveStats:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("cannot describe an empty series")
    return DescriptiveStats(
        count=int(arr.size),
        mean=float(arr.mean()),
        std=float(arr.std(ddof=1)) if arr.size >= 2 else None,
        minimum=float(arr.min()),
        maximum=float(arr.max()),
    )


def fit_linear_trend(days: np.ndarray, values: np.ndarray) -> TrendFit | None:
    """Least-squares trend of ``values`` against elapsed ``days``.

    Returns ``None`` when a fit is not meaningful: fewer than 3 points, or all
    timestamps identical. This is a descriptive fit, not a forecast.
    """
    x = np.asarray(days, dtype=float)
    y = np.asarray(values, dtype=float)
    if x.shape != y.shape:
        raise ValueError("days and values must have the same shape")
    if x.size < 3 or np.ptp(x) == 0.0:
        return None
    res = sp_stats.linregress(x, y)
    return TrendFit(
        slope_per_day=float(res.slope),
        intercept=float(res.intercept),
        r_value=float(res.rvalue),
        slope_stderr=float(res.stderr),
        count=int(x.size),
    )
