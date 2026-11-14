import numpy as np
import pytest

from conftest import make_obs
from medvital.modules.bone import SPEC
from medvital.modules.bone import calculations as calc
from medvital.modules.bone.service import summarize


def test_percent_change():
    assert calc.percent_change_from_baseline(1.0, 0.9) == pytest.approx(-10.0)
    assert calc.percent_change_from_baseline(2.0, 2.0) == 0.0


def test_percent_change_rejects_non_positive_baseline():
    with pytest.raises(ValueError):
        calc.percent_change_from_baseline(0.0, 1.0)


def test_percent_change_series():
    np.testing.assert_allclose(calc.percent_change_series(np.array([1.0, 0.5, 2.0])), [0.0, -50.0, 100.0])


def _bmd(values, days, site="femoral_neck"):
    return [
        make_obs("bone.areal_bmd", v, day=d, context={"site": site})
        for v, d in zip(values, days, strict=True)
    ]


def test_summary_percent_change_and_slope():
    s = summarize("SIM-T01", _bmd([1.0, 0.99, 0.98], [0, 10, 20]))
    by_name = {d.name: d for d in s.derived_values}
    assert by_name["percent_change_from_first_observation"].value == pytest.approx(-2.0)
    assert by_name["trend_slope_per_day"].value == pytest.approx(-0.001)


def test_sites_are_not_pooled():
    obs = _bmd([1.0, 0.9], [0, 10], "femoral_neck") + _bmd([1.2, 1.2], [0, 10], "lumbar_spine")
    s = summarize("SIM-T01", obs)
    pct = {d.context["site"]: d.value for d in s.derived_values if d.name.startswith("percent")}
    assert pct == {"femoral_neck": pytest.approx(-10.0), "lumbar_spine": pytest.approx(0.0)}


def test_insufficient_data_warns_instead_of_guessing():
    s = summarize("SIM-T01", _bmd([1.0], [0]))
    assert s.derived_values == []
    assert len(s.warnings) == 2


def test_two_points_gives_percent_but_no_trend():
    s = summarize("SIM-T01", _bmd([1.0, 0.9], [0, 5]))
    assert [d.name for d in s.derived_values] == ["percent_change_from_first_observation"]


def test_spec_metrics_belong_to_module():
    assert all(m.metric.startswith("bone.") for m in SPEC.metrics)


# --------------------------------------------------------------------------- M3 wiring: DXA vs QCT, uncertainty

from medvital.modules.bone.service import summarize as _summ  # noqa: E402


def _m3_bmd(metric, unit, value, day, site="femoral_neck", u=None):
    o = make_obs(metric, value, unit=unit, day=day, context={"site": site})
    return o.model_copy(update={"uncertainty": u})


def test_areal_and_volumetric_bmd_are_never_pooled():
    obs = [
        _m3_bmd("bone.areal_bmd", "g/cm2", 1.00, 0),
        _m3_bmd("bone.areal_bmd", "g/cm2", 0.98, 30),
        _m3_bmd("bone.volumetric_bmd", "mg/cm3", 300.0, 0),
        _m3_bmd("bone.volumetric_bmd", "mg/cm3", 291.0, 30),
    ]
    s = _summ("SIM-T01", obs)
    pct = {d.input_metric: d for d in s.derived_values if d.name == "percent_change_from_first_observation"}
    assert pct["bone.areal_bmd"].value == pytest.approx(-2.0) and pct["bone.areal_bmd"].unit == "%"
    assert pct["bone.volumetric_bmd"].value == pytest.approx(-3.0)  # 100*(291-300)/300
    assert {m.unit for m in s.metric_summaries if m.metric == "bone.volumetric_bmd"} == {"mg/cm3"}


def test_bmd_percent_change_uncertainty_propagated_only_when_known():
    # x0=1.0 (u .01), x=0.9 (u .02): u = 100*sqrt(1*.0004 + .81*.0001) = 100*sqrt(.000481)
    known = _summ(
        "SIM-T01",
        [_m3_bmd("bone.areal_bmd", "g/cm2", 1.0, 0, u=0.01), _m3_bmd("bone.areal_bmd", "g/cm2", 0.9, 30, u=0.02)],
    )
    (d,) = [d for d in known.derived_values if d.name == "percent_change_from_first_observation"]
    assert d.value == pytest.approx(-10.0) and d.uncertainty == pytest.approx(100 * 0.000481**0.5)
    unknown = _summ(
        "SIM-T01", [_m3_bmd("bone.areal_bmd", "g/cm2", 1.0, 0, u=0.01), _m3_bmd("bone.areal_bmd", "g/cm2", 0.9, 30)]
    )
    (d2,) = [d for d in unknown.derived_values if d.name == "percent_change_from_first_observation"]
    assert d2.uncertainty is None
