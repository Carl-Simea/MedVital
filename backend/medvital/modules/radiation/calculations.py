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


# Supported constant-rate units -> (dose unit, seconds per rate time-unit). Absorbed dose (Gy)
# and dose equivalent (Sv) stay separate: the output quantity always follows the input.
DOSE_RATE_UNITS: dict[str, tuple[str, float]] = {
    "uGy/h": ("uGy", 3600.0),
    "mGy/d": ("mGy", 86400.0),
    "uSv/h": ("uSv", 3600.0),
    "mSv/d": ("mSv", 86400.0),
}


def dose_from_constant_rate(dose_rate: float, *, rate_unit: str, elapsed_s: float) -> tuple[float, str]:
    """``D = dose_rate * elapsed_time`` for a rate assumed constant over the interval.

    Returns ``(dose, dose_unit)``. Never converts Gy to Sv (that needs radiation weighting) and
    never converts detector-material dose to tissue dose.
    """
    if rate_unit not in DOSE_RATE_UNITS:
        raise ValueError(f"unsupported dose-rate unit {rate_unit!r}; supported: {sorted(DOSE_RATE_UNITS)}")
    if not (np.isfinite(dose_rate) and dose_rate >= 0):
        raise ValueError("dose_rate must be finite and >= 0")
    if not (np.isfinite(elapsed_s) and elapsed_s >= 0):
        raise ValueError("elapsed_s must be finite and >= 0")
    dose_unit, seconds_per_unit = DOSE_RATE_UNITS[rate_unit]
    return float(dose_rate * elapsed_s / seconds_per_unit), dose_unit
