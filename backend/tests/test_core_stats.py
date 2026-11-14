"""core.stats.percent_change: hand-computed values and uncertainty semantics."""

import math

import pytest

from medvital.core.stats import percent_change


def test_percent_change_value():
    # 100 * (0.90 - 0.95) / 0.95 = -5.2631578947...
    r = percent_change(0.90, 0.95)
    assert r.value == pytest.approx(-100 * 0.05 / 0.95)
    assert r.uncertainty is None  # unknown uncertainty stays None, never 0


def test_percent_change_uncertainty_hand_computed():
    # x0 = 1.0 (u 0.01), x = 0.9 (u 0.02): value -10
    # u = 100/1^2 * sqrt(1^2*0.02^2 + 0.9^2*0.01^2) = 100*sqrt(0.0004 + 0.000081) = 100*sqrt(0.000481)
    r = percent_change(0.9, 1.0, u_current=0.02, u_baseline=0.01)
    assert r.value == pytest.approx(-10.0)
    assert r.uncertainty == pytest.approx(100 * math.sqrt(0.000481))  # 2.19317...


def test_partial_or_zero_uncertainty():
    assert percent_change(2.0, 1.0, u_current=0.1).uncertainty is None
    assert percent_change(2.0, 1.0, u_baseline=0.1).uncertainty is None
    assert percent_change(2.0, 1.0, u_current=0.0, u_baseline=0.0).uncertainty == 0.0  # explicitly known


def test_negative_baseline_gives_non_negative_uncertainty():
    # x0 = -2 (u 0), x = -1 (u 0.1): value 100*(1)/(-2) = -50; u = 100/4 * sqrt(4*0.01) = 25*0.2 = 5
    r = percent_change(-1.0, -2.0, u_current=0.1, u_baseline=0.0)
    assert r.value == pytest.approx(-50.0) and r.uncertainty == pytest.approx(5.0)


@pytest.mark.parametrize(
    "args",
    [(1.0, 0.0, None, None), (float("nan"), 1.0, None, None), (1.0, 1.0, -0.1, 0.1), (1.0, 1.0, 0.1, float("inf"))],
)
def test_percent_change_rejects_bad_input(args):
    with pytest.raises(ValueError):
        percent_change(*args)
