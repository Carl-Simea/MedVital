"""Pure behavioral-health arithmetic: personal-baseline deviation. No thresholds, no labels."""

from __future__ import annotations

import numpy as np
from sklearn.preprocessing import RobustScaler

# Engineering default, configurable per call. Not a clinical or scientific recommendation.
DEFAULT_BASELINE_WINDOW = 7
MIN_BASELINE_WINDOW = 4


def robust_deviation_from_baseline(
    values: np.ndarray, baseline_window: int = DEFAULT_BASELINE_WINDOW
) -> np.ndarray:
    """Deviation of every post-baseline value from the subject's *own* baseline.

    The first ``baseline_window`` values define the baseline. Deviation is
    ``(x - median) / IQR`` via ``sklearn.preprocessing.RobustScaler`` fitted on the
    baseline only (so later values never influence it). If the baseline IQR is zero,
    scikit-learn leaves the scale at 1, i.e. the deviation is in raw units.

    Returns one value per observation after the baseline window. The result says how
    far a value sits from the person's own earlier values — nothing more.
    """
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise ValueError("values must be one-dimensional")
    if baseline_window < MIN_BASELINE_WINDOW:
        raise ValueError(f"baseline_window must be >= {MIN_BASELINE_WINDOW}")
    if arr.size <= baseline_window:
        raise ValueError("need more observations than the baseline window")
    scaler = RobustScaler().fit(arr[:baseline_window].reshape(-1, 1))
    return scaler.transform(arr[baseline_window:].reshape(-1, 1)).ravel()


SLEEP_TIME_UNITS = ("h", "min", "s")


def sleep_efficiency(total_sleep_time: float, time_in_bed: float, *, unit: str) -> float:
    """``SE [%] = total_sleep_time / time_in_bed * 100`` (Hand & Siengsukon 2025, Sleep Adv 6(3):zpaf045).

    Both durations share ``unit``. The definition of *time in bed* varies between studies
    (literal in-bed interval vs. intention-to-sleep window), so callers must record which one
    was used and never pool results across definitions. No cut-off is applied.
    """
    if unit not in SLEEP_TIME_UNITS:
        raise ValueError(f"unit must be one of {SLEEP_TIME_UNITS}, got {unit!r}")
    if not (np.isfinite(total_sleep_time) and np.isfinite(time_in_bed)):
        raise ValueError("durations must be finite")
    if not time_in_bed > 0:
        raise ValueError("time_in_bed must be > 0")
    if not 0 <= total_sleep_time <= time_in_bed:
        raise ValueError("total_sleep_time must be between 0 and time_in_bed")
    return float(100.0 * total_sleep_time / time_in_bed)
