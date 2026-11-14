import numpy as np
import pytest

from conftest import make_obs
from medvital.modules.behavioral import SPEC
from medvital.modules.behavioral import calculations as calc
from medvital.modules.behavioral.service import summarize


def test_deviation_known_value():
    # baseline [1,2,3,4]: median 2.5, IQR 1.5 -> (4 - 2.5) / 1.5 = 1.0
    out = calc.robust_deviation_from_baseline(np.array([1.0, 2.0, 3.0, 4.0, 4.0]), baseline_window=4)
    np.testing.assert_allclose(out, [1.0])


def test_zero_iqr_baseline_falls_back_to_raw_units():
    out = calc.robust_deviation_from_baseline(np.array([2.0, 2.0, 2.0, 2.0, 5.0]), baseline_window=4)
    np.testing.assert_allclose(out, [3.0])


def test_baseline_not_influenced_by_later_values():
    base = [1.0, 2.0, 3.0, 4.0]
    a = calc.robust_deviation_from_baseline(np.array(base + [10.0]), 4)
    b = calc.robust_deviation_from_baseline(np.array(base + [10.0, 1000.0]), 4)
    assert a[0] == pytest.approx(b[0])


def test_requires_more_than_baseline():
    with pytest.raises(ValueError):
        calc.robust_deviation_from_baseline(np.array([1.0, 2.0, 3.0, 4.0]), 4)


def test_rejects_tiny_window():
    with pytest.raises(ValueError):
        calc.robust_deviation_from_baseline(np.arange(10.0), 2)


def _sleep(values):
    return [make_obs("behavioral.sleep_duration", v, day=i) for i, v in enumerate(values)]


def test_summary_deviation():
    s = summarize("SIM-T01", _sleep([1.0, 2.0, 3.0, 4.0, 4.0]), baseline_window=4)
    (d,) = s.derived_values
    assert d.value == pytest.approx(1.0)
    assert "clinical" in d.description


def test_short_series_warns():
    s = summarize("SIM-T01", _sleep([7.0, 7.0]))
    assert s.derived_values == [] and s.warnings


def test_instruments_are_not_pooled():
    def score(v, d, inst):
        return make_obs("behavioral.self_report_score", v, day=d, context={"instrument": inst})

    obs = [score(v, i, "A") for i, v in enumerate([1, 2, 3, 4, 4])] + [
        score(v, i, "B") for i, v in enumerate([10, 10, 10, 10, 10])
    ]
    s = summarize("SIM-T01", obs, baseline_window=4)
    got = {d.context["instrument"]: d.value for d in s.derived_values}
    assert got == {"A": pytest.approx(1.0), "B": pytest.approx(0.0)}


def test_spec_metrics_belong_to_module():
    assert all(m.metric.startswith("behavioral.") for m in SPEC.metrics)
