"""Radiation calculations: pure numerics, no schema or framework dependencies."""

from __future__ import annotations

from collections.abc import Sequence

from medvital.core.stats import trapezoid_integral


def cumulative_dose(times_days: Sequence[float], dose_rates: Sequence[float]) -> float:
    """Accumulated dose over a period: trapezoidal integral of dose rate over time.

    If rates are in uGy/day and times in days, the result is in uGy. This is arithmetic
    accumulation of supplied values; it is not a risk estimate and applies no limit.
    """
    return trapezoid_integral(times_days, dose_rates)
