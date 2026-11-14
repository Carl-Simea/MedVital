"""Exact unit conversions used by importers (multiplicative only).

Every factor here is a unit definition, not a measurement. Add a pair only if the factor is
exact or defined to the precision shown, and add a test with the hand-computed result.
"""

from __future__ import annotations

# (from_unit, to_unit) -> factor, so that value_in_to = value_in_from * factor
_FACTORS: dict[tuple[str, str], float] = {
    ("mGy/day", "uGy/day"): 1000.0,
    ("nGy/day", "uGy/day"): 0.001,
    ("Gy/day", "uGy/day"): 1_000_000.0,
    ("mGy", "uGy"): 1000.0,
    ("min", "h"): 1.0 / 60.0,
    ("s", "ms"): 1000.0,
    ("g/m2", "g/cm2"): 0.0001,
    # 1 mmHg = 133.322387415 Pa, so 1 kPa = 1000 / 133.322387415 mmHg
    ("kPa", "mmHg"): 1000.0 / 133.322387415,
}


def can_convert(from_unit: str, to_unit: str) -> bool:
    return from_unit == to_unit or (from_unit, to_unit) in _FACTORS


def convert(value: float, from_unit: str, to_unit: str) -> float:
    if from_unit == to_unit:
        return value
    try:
        return value * _FACTORS[(from_unit, to_unit)]
    except KeyError:
        raise ValueError(f"no conversion from '{from_unit}' to '{to_unit}'") from None
