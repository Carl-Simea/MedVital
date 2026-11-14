"""Pure analysis arithmetic: descriptive statistics, personal-baseline deviation,
sampling-gap/missingness measures and statistical outlier flags.

NumPy only. No ``medvital`` imports, no pydantic, no I/O (enforced by
``tests/test_analysis_architecture.py``). Nothing here knows about health, and nothing
here applies a clinical threshold. Every cutoff is a caller-supplied *statistical*
parameter.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Iglewicz & Hoaglin (1993), "How to Detect and Handle Outliers", ASQC Quality Press:
# modified z-score M = 0.6745 * (x - median) / MAD. 0.6745 is the 0.75 quantile of the
# standard normal distribution, which makes MAD consistent with the SD for normal data.
MODIFIED_Z_CONSTANT = 0.6745


# --------------------------------------------------------------------------- descriptive


@dataclass(frozen=True)
class Descriptive:
    count: int
    mean: float
    std: float | None  # sample standard deviation (ddof=1); None when count < 2
    median: float
    q1: float  # 25th percentile, linear interpolation (NumPy default)
    q3: float  # 75th percentile, linear interpolation
    iqr: float
    mad: float  # median absolute deviation from the median, unscaled
    minimum: float
    maximum: float


def _as_1d_finite(values: np.ndarray, name: str = "values") -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must be finite")
    return arr


def median_absolute_deviation(values: np.ndarray) -> float:
    """``median(|x - median(x)|)``, unscaled."""
    arr = _as_1d_finite(values)
    if arr.size == 0:
        raise ValueError("cannot compute MAD of an empty series")
    return float(np.median(np.abs(arr - np.median(arr))))


def describe(values: np.ndarray) -> Descriptive:
    arr = _as_1d_finite(values)
    if arr.size == 0:
        raise ValueError("cannot describe an empty series")
    q1, median, q3 = (float(v) for v in np.percentile(arr, [25, 50, 75]))
    return Descriptive(
        count=int(arr.size),
        mean=float(arr.mean()),
        std=float(arr.std(ddof=1)) if arr.size >= 2 else None,
        median=median,
        q1=q1,
        q3=q3,
        iqr=q3 - q1,
        mad=median_absolute_deviation(arr),
        minimum=float(arr.min()),
        maximum=float(arr.max()),
    )


# --------------------------------------------------------------------------- baseline


def first_n_mask(size: int, n: int) -> np.ndarray:
    """Boolean mask selecting the first ``n`` of ``size`` time-ordered points."""
    if n < 1:
        raise ValueError("n must be >= 1")
    mask = np.zeros(size, dtype=bool)
    mask[: min(n, size)] = True
    return mask


def window_mask(times_s: np.ndarray, start_s: float, end_s: float) -> np.ndarray:
    """Boolean mask of points with ``start_s <= t < end_s`` (half-open window)."""
    if not end_s > start_s:
        raise ValueError("baseline window end must be after start")
    t = _as_1d_finite(times_s, "times_s")
    return (t >= start_s) & (t < end_s)


@dataclass(frozen=True)
class Deviations:
    """Per-value deviation from a baseline. ``NaN`` where a measure is undefined."""

    delta: np.ndarray  # x - baseline median, in the series' own unit
    z: np.ndarray  # (x - baseline mean) / baseline SD; NaN if SD undefined or zero
    modified_z: np.ndarray  # 0.6745 (x - baseline median) / baseline MAD; NaN if MAD is zero


def deviations_from_baseline(values: np.ndarray, baseline: Descriptive) -> Deviations:
    arr = _as_1d_finite(values)
    delta = arr - baseline.median
    if baseline.std is not None and baseline.std > 0:
        z = (arr - baseline.mean) / baseline.std
    else:
        z = np.full(arr.shape, np.nan)
    if baseline.mad > 0:
        mz = MODIFIED_Z_CONSTANT * delta / baseline.mad
    else:
        mz = np.full(arr.shape, np.nan)
    return Deviations(delta=delta, z=z, modified_z=mz)


# --------------------------------------------------------------------------- outliers


def flag_modified_z(modified_z: np.ndarray, cutoff: float) -> np.ndarray:
    """``|M| > cutoff``. NaN (undefined) never flags. A statistical flag, not a finding."""
    if not cutoff > 0:
        raise ValueError("cutoff must be > 0")
    mz = np.asarray(modified_z, dtype=float)
    with np.errstate(invalid="ignore"):
        return np.abs(mz) > cutoff


# --------------------------------------------------------------------------- sampling / missingness


def count_duplicate_times(times_s: np.ndarray) -> int:
    """Observations sharing an exact timestamp with an earlier one."""
    t = _as_1d_finite(times_s, "times_s")
    return int(t.size - np.unique(t).size)


def median_interval(times_s: np.ndarray) -> float | None:
    """Median positive spacing between sorted distinct timestamps; None if < 2 distinct."""
    t = np.unique(_as_1d_finite(times_s, "times_s"))
    if t.size < 2:
        return None
    return float(np.median(np.diff(t)))


@dataclass(frozen=True)
class Gap:
    start_index: int  # index (into the sorted distinct times) of the point before the gap
    end_index: int  # index of the point after the gap
    duration_s: float


def find_gaps(times_s: np.ndarray, expected_interval_s: float, gap_factor: float) -> list[Gap]:
    """Spacings strictly greater than ``gap_factor * expected_interval_s``.

    Indices refer to the sorted array of *distinct* timestamps.
    """
    if not expected_interval_s > 0:
        raise ValueError("expected_interval_s must be > 0")
    if not gap_factor >= 1:
        raise ValueError("gap_factor must be >= 1")
    t = np.unique(_as_1d_finite(times_s, "times_s"))
    if t.size < 2:
        return []
    d = np.diff(t)
    idx = np.flatnonzero(d > gap_factor * expected_interval_s)
    return [Gap(int(i), int(i + 1), float(d[i])) for i in idx]


def expected_count(times_s: np.ndarray, expected_interval_s: float) -> int:
    """Points expected between the first and last timestamp at the given cadence (inclusive)."""
    if not expected_interval_s > 0:
        raise ValueError("expected_interval_s must be > 0")
    t = _as_1d_finite(times_s, "times_s")
    if t.size == 0:
        return 0
    return int(np.floor((t.max() - t.min()) / expected_interval_s)) + 1


def coverage_fraction(times_s: np.ndarray, expected_interval_s: float) -> float | None:
    """Distinct observed timestamps / expected count, capped at 1.0. None if nothing expected."""
    expected = expected_count(times_s, expected_interval_s)
    if expected == 0:
        return None
    observed = np.unique(_as_1d_finite(times_s, "times_s")).size
    return float(min(1.0, observed / expected))
