"""Pure bone-density arithmetic. No I/O, no schema types, no clinical thresholds."""

from __future__ import annotations

import numpy as np


def percent_change_from_baseline(baseline: float, current: float) -> float:
    """``100 * (current - baseline) / baseline``. Baseline must be strictly positive."""
    if not baseline > 0:
        raise ValueError("baseline must be > 0")
    return 100.0 * (current - baseline) / baseline


def percent_change_series(values: np.ndarray) -> np.ndarray:
    """Percent change of every value relative to the first (earliest) value."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        raise ValueError("no values")
    base = arr[0]
    if not base > 0:
        raise ValueError("baseline must be > 0")
    return 100.0 * (arr - base) / base
