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


@dataclass(frozen=True)
class PercentChange:
    """``value`` in percent; ``uncertainty`` is a standard uncertainty in percentage points,
    or ``None`` when any input uncertainty is unknown (never silently 0)."""

    value: float
    uncertainty: float | None


def percent_change(
    current: float,
    baseline: float,
    u_current: float | None = None,
    u_baseline: float | None = None,
) -> PercentChange:
    """``100 * (current - baseline) / baseline`` with first-order uncertainty propagation.

    ``u(Δ%) = (100 / baseline²) * sqrt(baseline² u(current)² + current² u(baseline)²)``, assuming
    independent inputs (derivation: docs/MODELING_GAP_ANALYSIS.md F2). Both values must be in
    the same unit — the caller guarantees this by taking them from one series.
    """
    for name, v in (("current", current), ("baseline", baseline)):
        if not np.isfinite(v):
            raise ValueError(f"{name} must be finite")
    if baseline == 0:
        raise ValueError("baseline must be non-zero")
    for name, u in (("u_current", u_current), ("u_baseline", u_baseline)):
        if u is not None and (not np.isfinite(u) or u < 0):
            raise ValueError(f"{name} must be a finite value >= 0, or None if unknown")
    value = 100.0 * (current - baseline) / baseline
    if u_current is None or u_baseline is None:
        return PercentChange(value=value, uncertainty=None)
    u = 100.0 / baseline**2 * float(np.sqrt(baseline**2 * u_current**2 + current**2 * u_baseline**2))
    return PercentChange(value=value, uncertainty=abs(u))
