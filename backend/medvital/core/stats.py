"""Generic statistical building blocks (NumPy / SciPy / scikit-learn).

Pure functions on arrays. No observation schema, no web framework, no presentation concerns.
Nothing here encodes a clinical threshold or makes a diagnosis.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from scipy import integrate, stats
from sklearn.ensemble import IsolationForest

_SECONDS_PER_DAY = 86400.0


@dataclass(frozen=True)
class SeriesStats:
    n: int
    mean: float
    std: float | None  # sample standard deviation (ddof=1); None when n < 2
    slope_per_day: float | None  # least-squares slope; None when n < 3 or times are identical


def series_stats(times: Sequence[datetime], values: Sequence[float]) -> SeriesStats:
    """Descriptive statistics and an ordinary least-squares trend for one time series."""
    if len(times) != len(values):
        raise ValueError("times and values must have the same length")
    v = np.asarray(values, dtype=float)
    if v.size == 0:
        raise ValueError("series must not be empty")
    std = float(np.std(v, ddof=1)) if v.size > 1 else None
    slope: float | None = None
    if v.size >= 3:
        t = np.array([ts.timestamp() for ts in times], dtype=float) / _SECONDS_PER_DAY
        if np.ptp(t) > 0:
            slope = float(stats.linregress(t, v).slope)
    return SeriesStats(n=int(v.size), mean=float(np.mean(v)), std=std, slope_per_day=slope)


def baseline_z_scores(values: Sequence[float], baseline_n: int) -> np.ndarray:
    """Z-scores of every value against the mean/SD of the first ``baseline_n`` values.

    This describes deviation from a person's own early values. It is not a normal range.
    Returns NaN everywhere when the baseline has zero spread.
    """
    v = np.asarray(values, dtype=float)
    if baseline_n < 2:
        raise ValueError("baseline_n must be at least 2")
    if v.size < baseline_n:
        raise ValueError("not enough values for the requested baseline window")
    base = v[:baseline_n]
    sd = float(np.std(base, ddof=1))
    if sd == 0.0:
        return np.full(v.shape, np.nan)
    return (v - float(np.mean(base))) / sd


def multivariate_outlier_scores(matrix: np.ndarray, seed: int) -> np.ndarray:
    """Relative outlier score per row (higher = more unusual within this matrix).

    Uses scikit-learn's IsolationForest with a fixed seed. The score is a statistical
    statement about the supplied data only; it carries no clinical meaning.
    """
    x = np.asarray(matrix, dtype=float)
    if x.ndim != 2 or x.shape[0] < 2:
        raise ValueError("matrix must be 2-D with at least 2 rows")
    forest = IsolationForest(n_estimators=100, random_state=seed).fit(x)
    return -forest.score_samples(x)


def trapezoid_integral(x: Sequence[float], y: Sequence[float]) -> float:
    """Trapezoidal-rule integral of y over x."""
    if len(x) != len(y):
        raise ValueError("x and y must have the same length")
    if len(x) < 2:
        raise ValueError("at least two points are required")
    return float(integrate.trapezoid(np.asarray(y, dtype=float), np.asarray(x, dtype=float)))
