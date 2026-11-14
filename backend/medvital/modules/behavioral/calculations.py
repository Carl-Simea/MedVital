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
