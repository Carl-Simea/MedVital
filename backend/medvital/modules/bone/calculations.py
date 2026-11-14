"""Bone health calculations: pure numerics, no schema or framework dependencies."""

from __future__ import annotations


def percent_change(baseline: float, current: float) -> float:
    """Relative change from a baseline value, in percent. Baseline must be positive."""
    if baseline <= 0:
        raise ValueError("baseline must be positive")
    return (current - baseline) / baseline * 100.0
