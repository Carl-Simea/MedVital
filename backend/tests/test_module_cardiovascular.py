import numpy as np
import pytest

from conftest import make_obs
from medvital.modules.cardiovascular import SPEC
from medvital.modules.cardiovascular import calculations as calc
from medvital.modules.cardiovascular.service import summarize


def test_rmssd_known_value():
    # diffs: +10, -20 -> sqrt((100 + 400) / 2)
    assert calc.rmssd(np.array([800.0, 810.0, 790.0])) == pytest.approx(np.sqrt(250.0))


def test_rmssd_constant_series_is_zero():
    assert calc.rmssd(np.array([800.0] * 5)) == 0.0


def test_rmssd_needs_three_intervals():
    with pytest.raises(ValueError):
        calc.rmssd(np.array([800.0, 810.0]))


def test_rmssd_rejects_non_positive():
    with pytest.raises(ValueError):
        calc.rmssd(np.array([800.0, 0.0, 790.0]))


def _rr(values, session):
    return [
        make_obs("cardiovascular.rr_interval", v, day=i / 86400, context={"session_id": session})
        for i, v in enumerate(values)
    ]


def test_rmssd_per_session_not_pooled():
    obs = _rr([800, 810, 790], "a") + _rr([1000, 1000, 1000], "b")
    s = summarize("SIM-T01", obs)
    got = {d.context["session_id"]: d.value for d in s.derived_values if d.name == "rmssd"}
    assert got == {"a": pytest.approx(np.sqrt(250.0)), "b": 0.0}


def test_short_session_warns():
    s = summarize("SIM-T01", _rr([800, 810], "short"))
    assert s.derived_values == []
    assert any("short" in w for w in s.warnings)


def test_heart_rate_descriptive_stats():
    obs = [make_obs("cardiovascular.resting_heart_rate", v, day=i) for i, v in enumerate([60, 62, 64])]
    (m,) = summarize("SIM-T01", obs).metric_summaries
    assert m.mean == pytest.approx(62.0) and m.count == 3 and m.unit == "{beats}/min"


def test_spec_metrics_belong_to_module():
    assert all(m.metric.startswith("cardiovascular.") for m in SPEC.metrics)
