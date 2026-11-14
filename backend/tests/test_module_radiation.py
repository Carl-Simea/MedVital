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


def test_dose_from_constant_rate_hand_computed():
    # 10 uGy/h * 7200 s / 3600 = 20 uGy ; 0.5 mGy/d * 3 d (259200 s) / 86400 = 1.5 mGy
    assert calc.dose_from_constant_rate(10, rate_unit="uGy/h", elapsed_s=7200) == pytest.approx((20.0, "uGy"))
    assert calc.dose_from_constant_rate(0.5, rate_unit="mGy/d", elapsed_s=3 * 86400) == pytest.approx(
        (1.5, "mGy")
    )
    assert calc.dose_from_constant_rate(0.0, rate_unit="uGy/h", elapsed_s=3600) == (0.0, "uGy")


def test_dose_quantity_is_preserved_never_gy_to_sv():
    dose, unit = calc.dose_from_constant_rate(2, rate_unit="uSv/h", elapsed_s=1800)  # 2 * 0.5 h = 1 uSv
    assert (dose, unit) == (pytest.approx(1.0), "uSv")
    assert calc.dose_from_constant_rate(1, rate_unit="mSv/d", elapsed_s=86400)[1] == "mSv"


@pytest.mark.parametrize(
    "rate,unit,elapsed",
    [(1, "Gy/s", 10), (1, "uGy/min", 10), (-1, "uGy/h", 10), (1, "uGy/h", -5), (float("nan"), "uGy/h", 1)],
)
def test_dose_from_constant_rate_validates(rate, unit, elapsed):
    with pytest.raises(ValueError):
        calc.dose_from_constant_rate(rate, rate_unit=unit, elapsed_s=elapsed)


# --------------------------------------------------------------------------- M3 wiring: dose-rate integration

from datetime import timedelta as _td  # noqa: E402


def _rate(value, hours):
    o = make_obs("radiation.dose_rate", value, unit="uGy/h", context={"instrument": "DOSI-1"})
    t = o.observed_at + _td(hours=hours)
    return o.model_copy(update={"observed_at": t, "recorded_at": t})


def test_dose_rate_integration_hand_computed():
    # samples at 0,1,2 h of 10 uGy/h: two 1 h intervals -> 10*1 + 10*1 = 20 uGy (last sample opens no interval)
    s = summarize("SIM-T01", [_rate(10, 0), _rate(10, 1), _rate(10, 2)])
    (d,) = [d for d in s.derived_values if d.name == "integrated_dose_over_sampled_intervals"]
    assert d.value == pytest.approx(20.0) and d.unit == "uGy" and d.data_origin.value == "modeled"


def test_dose_rate_long_gap_not_integrated():
    # intervals 1 h, 1 h, 5 h: median 1 h -> max gap 2 h; the 5 h gap is excluded (lower bound) and reported
    s = summarize("SIM-T01", [_rate(10, 0), _rate(20, 1), _rate(10, 2), _rate(10, 7)])
    (d,) = [d for d in s.derived_values if d.name == "integrated_dose_over_sampled_intervals"]
    assert d.value == pytest.approx(10 * 1 + 20 * 1)
    assert any("not integrated" in w for w in s.warnings)
