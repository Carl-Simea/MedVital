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


def test_cardiac_output_hand_computed():
    # 60 beats/min * 70 mL / 1000 = 4.2 L/min ; 72 * 80 / 1000 = 5.76
    kw = dict(heart_rate_unit="{beats}/min", stroke_volume_unit="mL")
    assert calc.cardiac_output(60, 70, **kw) == pytest.approx(4.2)
    assert calc.cardiac_output(72, 80, **kw) == pytest.approx(5.76)


@pytest.mark.parametrize(
    "hr,sv,hr_unit,sv_unit",
    [(60, 70, "bpm", "mL"), (60, 70, "{beats}/min", "L"), (0, 70, "{beats}/min", "mL"), (60, -1, "{beats}/min", "mL")],
)
def test_cardiac_output_validates_units_and_inputs(hr, sv, hr_unit, sv_unit):
    with pytest.raises(ValueError):
        calc.cardiac_output(hr, sv, heart_rate_unit=hr_unit, stroke_volume_unit=sv_unit)


def test_map_estimate_hand_computed():
    # 80 + (120 - 80)/3 = 93.333... ; 60 + (90 - 60)/3 = 70 ; equal pressures -> that pressure
    assert calc.mean_arterial_pressure_estimate(120, 80, unit="mm[Hg]") == pytest.approx(80 + 40 / 3)
    assert calc.mean_arterial_pressure_estimate(90, 60, unit="mm[Hg]") == pytest.approx(70.0)
    assert calc.mean_arterial_pressure_estimate(70, 70, unit="mm[Hg]") == pytest.approx(70.0)


@pytest.mark.parametrize("sbp,dbp,unit", [(120, 80, "mmHg"), (80, 120, "mm[Hg]"), (120, 0, "mm[Hg]")])
def test_map_estimate_validates(sbp, dbp, unit):
    with pytest.raises(ValueError):
        calc.mean_arterial_pressure_estimate(sbp, dbp, unit=unit)
