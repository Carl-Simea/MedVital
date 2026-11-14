import numpy as np
import pytest

from conftest import make_obs, measured_provenance
from medvital.core.schema import DataOrigin
from medvital.modules.radiation import SPEC
from medvital.modules.radiation import calculations as calc
from medvital.modules.radiation.service import summarize


def test_cumulative_dose_known_values():
    np.testing.assert_allclose(calc.cumulative_dose(np.array([1.0, 2.0, 3.0])), [1.0, 3.0, 6.0])


def test_cumulative_dose_rejects_negative():
    with pytest.raises(ValueError):
        calc.cumulative_dose(np.array([1.0, -1.0]))


def test_mean_daily_dose():
    assert calc.mean_daily_dose(np.array([1.0, 2.0, 6.0])) == pytest.approx(3.0)


def test_duplicate_day_count():
    assert calc.count_duplicate_days(np.array([20300101, 20300101, 20300102])) == 1


def _daily(values, **kw):
    return [make_obs("radiation.absorbed_dose_daily", v, day=i, **kw) for i, v in enumerate(values)]


def test_summary_values():
    s = summarize("SIM-T01", _daily([1.0, 2.0, 3.0]))
    by_name = {d.name: d for d in s.derived_values}
    assert by_name["cumulative_dose_over_observed_days"].value == pytest.approx(6.0)
    assert by_name["cumulative_dose_over_observed_days"].unit == "mGy"
    assert by_name["mean_daily_dose"].value == pytest.approx(2.0)
    assert by_name["mean_daily_dose"].unit == "mGy/d"
    assert s.warnings == []


def test_derived_values_are_labelled_modeled_with_input_origin():
    s = summarize("SIM-T01", _daily([1.0, 2.0]))
    for d in s.derived_values:
        assert d.data_origin is DataOrigin.MODELED
        assert d.input_origin is DataOrigin.SIMULATED


def test_origins_are_never_pooled():
    obs = _daily([1.0, 1.0]) + _daily([10.0, 10.0], provenance=measured_provenance())
    s = summarize("SIM-T01", obs)
    cum = [d for d in s.derived_values if d.name == "cumulative_dose_over_observed_days"]
    assert {(d.input_origin, d.value) for d in cum} == {
        (DataOrigin.SIMULATED, 2.0),
        (DataOrigin.MEASURED, 20.0),
    }


def test_warns_on_duplicate_days():
    obs = [make_obs(value=1.0, day=0), make_obs(value=1.0, day=0)]
    assert any("share a day" in w for w in summarize("SIM-T01", obs).warnings)


def test_other_subjects_and_modules_ignored():
    obs = _daily([1.0]) + [make_obs(value=9.0, subject_id="SIM-OTHER")]
    assert summarize("SIM-T01", obs).observation_count == 1


def test_empty_input_is_fine():
    s = summarize("SIM-T01", [])
    assert s.derived_values == [] and s.observation_count == 0


def test_summary_carries_non_diagnostic_notice():
    assert "Not a diagnosis" in summarize("SIM-T01", _daily([1.0])).notice


def test_spec_metrics_belong_to_module():
    assert all(m.metric.startswith("radiation.") for m in SPEC.metrics)
