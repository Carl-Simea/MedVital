from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from medvital.core.stats import (
    baseline_z_scores,
    multivariate_outlier_scores,
    series_stats,
    trapezoid_integral,
)

T0 = datetime(2030, 1, 1, tzinfo=UTC)


def test_series_stats_linear_series_has_exact_slope():
    times = [T0 + timedelta(days=d) for d in range(5)]
    values = [10.0, 12.0, 14.0, 16.0, 18.0]
    st = series_stats(times, values)
    assert st.n == 5
    assert st.mean == pytest.approx(14.0)
    assert st.std == pytest.approx(np.std(values, ddof=1))
    assert st.slope_per_day == pytest.approx(2.0)


def test_series_stats_small_samples():
    one = series_stats([T0], [3.0])
    assert one.std is None and one.slope_per_day is None
    two = series_stats([T0, T0 + timedelta(days=1)], [1.0, 2.0])
    assert two.std is not None and two.slope_per_day is None


def test_series_stats_identical_times_has_no_slope():
    st = series_stats([T0, T0, T0], [1.0, 2.0, 3.0])
    assert st.slope_per_day is None


def test_series_stats_validates_input():
    with pytest.raises(ValueError):
        series_stats([], [])
    with pytest.raises(ValueError):
        series_stats([T0], [1.0, 2.0])


def test_baseline_z_scores():
    z = baseline_z_scores([10.0, 12.0, 14.0, 22.0], baseline_n=3)
    # baseline mean 12, sample sd 2
    assert z.tolist() == pytest.approx([-1.0, 0.0, 1.0, 5.0])


def test_baseline_z_scores_zero_spread_is_nan_and_bad_args_raise():
    assert np.isnan(baseline_z_scores([5.0, 5.0, 5.0, 6.0], baseline_n=3)).all()
    with pytest.raises(ValueError):
        baseline_z_scores([1.0, 2.0], baseline_n=3)
    with pytest.raises(ValueError):
        baseline_z_scores([1.0, 2.0], baseline_n=1)


def test_outlier_scores_are_deterministic_and_rank_the_outlier_highest():
    rng = np.random.default_rng(0)
    data = rng.normal(0.0, 1.0, size=(100, 2))
    data = np.vstack([data, [[25.0, 25.0]]])
    first = multivariate_outlier_scores(data, seed=3)
    second = multivariate_outlier_scores(data, seed=3)
    assert np.array_equal(first, second)
    assert int(np.argmax(first)) == 100


def test_outlier_scores_validate_shape():
    with pytest.raises(ValueError):
        multivariate_outlier_scores(np.array([1.0, 2.0, 3.0]), seed=0)
    with pytest.raises(ValueError):
        multivariate_outlier_scores(np.array([[1.0, 2.0]]), seed=0)


def test_trapezoid_integral():
    assert trapezoid_integral([0, 1, 2], [0, 2, 4]) == pytest.approx(4.0)
    with pytest.raises(ValueError):
        trapezoid_integral([0], [1])
    with pytest.raises(ValueError):
        trapezoid_integral([0, 1], [1])
