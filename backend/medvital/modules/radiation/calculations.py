"""Pure radiation-dose arithmetic. No I/O, no schema types, no thresholds."""

from __future__ import annotations

import numpy as np


def cumulative_dose(daily_doses: np.ndarray) -> np.ndarray:
    """Running sum of time-ordered daily dose values.

    Sums only the days supplied; missing days are *not* imputed, so the result is a
    lower bound on true accumulation when there are gaps.
    """
    arr = np.asarray(daily_doses, dtype=float)
    if arr.ndim != 1:
        raise ValueError("daily_doses must be one-dimensional")
    if np.any(arr < 0):
        raise ValueError("daily doses cannot be negative")
    return np.cumsum(arr)


def mean_daily_dose(daily_doses: np.ndarray) -> float:
    arr = np.asarray(daily_doses, dtype=float)
    if arr.size == 0:
        raise ValueError("no dose values")
    return float(arr.mean())


def count_duplicate_days(day_ordinals: np.ndarray) -> int:
    """Number of observations that share a calendar day with an earlier one.

    Daily-integral metrics assume one value per day; duplicates would double-count.
    """
    arr = np.asarray(day_ordinals)
    return int(arr.size - np.unique(arr).size)
