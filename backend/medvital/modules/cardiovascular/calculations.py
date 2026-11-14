"""Pure cardiovascular arithmetic. No I/O, no schema types, no clinical thresholds."""

from __future__ import annotations

import numpy as np


def rmssd(rr_intervals_ms: np.ndarray) -> float:
    """Root mean square of successive differences of RR intervals (ms).

    Standard time-domain heart-rate-variability statistic. Requires >= 3 intervals
    (>= 2 successive differences). Input is assumed to be time-ordered and already
    artefact-free: this function performs **no** ectopic-beat or artefact correction.
    """
    rr = np.asarray(rr_intervals_ms, dtype=float)
    if rr.ndim != 1:
        raise ValueError("rr_intervals_ms must be one-dimensional")
    if rr.size < 3:
        raise ValueError("RMSSD needs at least 3 RR intervals")
    if np.any(rr <= 0):
        raise ValueError("RR intervals must be > 0")
    diffs = np.diff(rr)
    return float(np.sqrt(np.mean(diffs**2)))
