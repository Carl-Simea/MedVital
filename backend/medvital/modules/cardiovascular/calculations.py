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


HEART_RATE_UNIT = "{beats}/min"
STROKE_VOLUME_UNIT = "mL"
PRESSURE_UNIT = "mm[Hg]"
CARDIAC_OUTPUT_UNIT = "L/min"


def _require_unit(actual: str, expected: str, what: str) -> None:
    if actual != expected:
        raise ValueError(f"{what} must be in {expected!r}, got {actual!r}")


def cardiac_output(
    heart_rate: float, stroke_volume: float, *, heart_rate_unit: str, stroke_volume_unit: str
) -> float:
    """``CO [L/min] = HR [{beats}/min] * SV [mL] / 1000``. Definition plus unit conversion.

    Units are explicit and checked; anything else is rejected rather than converted.
    """
    _require_unit(heart_rate_unit, HEART_RATE_UNIT, "heart_rate")
    _require_unit(stroke_volume_unit, STROKE_VOLUME_UNIT, "stroke_volume")
    if not (np.isfinite(heart_rate) and heart_rate > 0):
        raise ValueError("heart_rate must be finite and > 0")
    if not (np.isfinite(stroke_volume) and stroke_volume > 0):
        raise ValueError("stroke_volume must be finite and > 0")
    return float(heart_rate * stroke_volume / 1000.0)


def mean_arterial_pressure_estimate(systolic: float, diastolic: float, *, unit: str) -> float:
    """``MAP ≈ DBP + (SBP - DBP) / 3`` — a conventional *approximation*, not a measurement.

    Its citation is not yet verified at source (docs/MODELING_GAP_ANALYSIS.md G-7); results must be
    labelled as an uncited estimate. Requires paired readings with ``SBP >= DBP > 0``.
    """
    _require_unit(unit, PRESSURE_UNIT, "blood pressure")
    if not (np.isfinite(systolic) and np.isfinite(diastolic)):
        raise ValueError("pressures must be finite")
    if not diastolic > 0:
        raise ValueError("diastolic must be > 0")
    if systolic < diastolic:
        raise ValueError("systolic must be >= diastolic")
    return float(diastolic + (systolic - diastolic) / 3.0)
