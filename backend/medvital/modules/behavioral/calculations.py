"""Behavioral health calculations: pure numerics, no schema or framework dependencies."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def trailing_mean(values: Sequence[float], window: int) -> float:
    """Mean of the last ``window`` values. Requires at least ``window`` values."""
    if window < 1:
        raise ValueError("window must be at least 1")
    if len(values) < window:
        raise ValueError("not enough values for the requested window")
    return float(np.mean(np.asarray(values, dtype=float)[-window:]))
