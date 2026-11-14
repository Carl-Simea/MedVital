"""Pure analysis arithmetic. Expected values are computed by hand in the comments."""

import math

import numpy as np
import pytest

from medvital.analysis import calculations as calc


def test_describe_hand_computed():
    # [1,2,3,4,10]: mean 4; deviations -3,-2,-1,0,6 -> SS 50 -> var 12.5 -> sd 3.5355339
    # quartiles (linear) 2 and 4; |x-3| = 2,1,0,1,7 -> MAD 1
    s = calc.describe(np.array([1, 2, 3, 4, 10]))
    assert s.count == 5
    assert s.mean == pytest.approx(4.0)
    assert s.std == pytest.approx(math.sqrt(12.5))
    assert (s.median, s.q1, s.q3, s.iqr, s.mad) == (3.0, 2.0, 4.0, 2.0, 1.0)
    assert (s.minimum, s.maximum) == (1.0, 10.0)


def test_describe_single_value_has_no_sd_and_rejects_bad_input():
    assert calc.describe(np.array([5.0])).std is None
    with pytest.raises(ValueError):
        calc.describe(np.array([]))
    with pytest.raises(ValueError):
        calc.describe(np.array([1.0, np.nan]))
    with pytest.raises(ValueError):
        calc.describe(np.ones((2, 2)))


def test_deviations_from_baseline_hand_computed():
    # baseline [1..5]: median 3, MAD 1, mean 3, sd sqrt(2.5)=1.5811388
    base = calc.describe(np.array([1, 2, 3, 4, 5]))
    d = calc.deviations_from_baseline(np.array([6.0, 9.0]), base)
    assert d.delta.tolist() == [3.0, 6.0]
    assert d.modified_z == pytest.approx([0.6745 * 3, 0.6745 * 6])  # 2.0235, 4.047
    assert d.z == pytest.approx([3 / math.sqrt(2.5), 6 / math.sqrt(2.5)])


def test_zero_spread_baseline_gives_undefined_scores():
    base = calc.describe(np.array([2.0, 2.0, 2.0, 2.0]))
    d = calc.deviations_from_baseline(np.array([3.0]), base)
    assert d.delta.tolist() == [1.0]
    assert np.isnan(d.z).all() and np.isnan(d.modified_z).all()


def test_flag_modified_z():
    flags = calc.flag_modified_z(np.array([2.0235, 4.047, -3.6, np.nan]), cutoff=3.5)
    assert flags.tolist() == [False, True, True, False]
    with pytest.raises(ValueError):
        calc.flag_modified_z(np.array([1.0]), cutoff=0)


def test_masks():
    assert calc.first_n_mask(5, 3).tolist() == [True, True, True, False, False]
    assert calc.first_n_mask(2, 3).tolist() == [True, True]
    assert calc.window_mask(np.array([0.0, 5.0, 10.0]), 0.0, 10.0).tolist() == [True, True, False]
    with pytest.raises(ValueError):
        calc.window_mask(np.array([0.0]), 5.0, 5.0)


def test_sampling_measures_hand_computed():
    t = np.array([0.0, 60.0, 120.0, 400.0, 460.0])
    # diffs 60,60,280,60 -> median 60; 280 > 2*60 is the only gap
    assert calc.median_interval(t) == 60.0
    gaps = calc.find_gaps(t, 60.0, 2.0)
    assert [(g.start_index, g.end_index, g.duration_s) for g in gaps] == [(2, 3, 280.0)]
    # floor(460/60)+1 = 8 expected; 5 observed -> 0.625
    assert calc.expected_count(t, 60.0) == 8
    assert calc.coverage_fraction(t, 60.0) == pytest.approx(0.625)


def test_duplicates_and_degenerate_sampling():
    assert calc.count_duplicate_times(np.array([0.0, 0.0, 60.0])) == 1
    assert calc.median_interval(np.array([5.0, 5.0])) is None
    assert calc.find_gaps(np.array([5.0]), 60.0, 2.0) == []
    with pytest.raises(ValueError):
        calc.find_gaps(np.array([0.0, 1.0]), 0.0, 2.0)
