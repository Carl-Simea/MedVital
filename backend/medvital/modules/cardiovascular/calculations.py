"""Cardiovascular calculations: pure numerics, no schema or framework dependencies."""

from __future__ import annotations


def mean_arterial_pressure(systolic: float, diastolic: float) -> float:
    """Common approximation: diastolic + one third of pulse pressure (mmHg)."""
    if systolic < diastolic:
        raise ValueError("systolic must not be lower than diastolic")
    return diastolic + (systolic - diastolic) / 3.0
