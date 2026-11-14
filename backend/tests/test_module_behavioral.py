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


def test_sleep_efficiency_hand_computed():
    # 6 h / 8 h * 100 = 75 ; 420 min / 480 min * 100 = 87.5 ; 0 / 8 = 0
    assert calc.sleep_efficiency(6, 8, unit="h") == pytest.approx(75.0)
    assert calc.sleep_efficiency(420, 480, unit="min") == pytest.approx(87.5)
    assert calc.sleep_efficiency(0, 8, unit="h") == 0.0
    assert calc.sleep_efficiency(8, 8, unit="h") == 100.0


@pytest.mark.parametrize(
    "tst,tib,unit", [(9, 8, "h"), (-1, 8, "h"), (1, 0, "h"), (6, 8, "hours"), (6, 8, "%")]
)
def test_sleep_efficiency_validates(tst, tib, unit):
    with pytest.raises(ValueError):
        calc.sleep_efficiency(tst, tib, unit=unit)


# --------------------------------------------------------------------------- M3 wiring: sleep efficiency

from medvital.registry import build_registry as _reg  # noqa: E402


def _m3_sleep(metric, value, tib_def=None, day=0):
    ctx = {"tib_definition": tib_def} if tib_def else {}
    return make_obs(metric, value, unit="h", day=day, context=ctx)


def test_sleep_efficiency_from_paired_period_hand_computed():
    s = summarize(
        "SIM-T01",
        [_m3_sleep("behavioral.sleep_duration", 6.0), _m3_sleep("behavioral.time_in_bed", 8.0, "literal_in_bed")],
    )
    (d,) = [d for d in s.derived_values if d.name == "sleep_efficiency"]
    assert (
        d.value == pytest.approx(75.0) and d.unit == "%" and d.context == {"tib_definition": "literal_in_bed"}
    )
    assert "zpaf045" in d.method


def test_tib_definitions_are_never_pooled_and_required():
    obs = [
        _m3_sleep("behavioral.sleep_duration", 6.0, day=0),
        _m3_sleep("behavioral.time_in_bed", 8.0, "literal_in_bed", day=0),
        _m3_sleep("behavioral.sleep_duration", 6.0, day=1),
        _m3_sleep("behavioral.time_in_bed", 7.5, "intention_to_sleep", day=1),
    ]
    defs = {
        d.context["tib_definition"]
        for d in summarize("SIM-T01", obs).derived_values
        if d.name == "sleep_efficiency"
    }
    assert defs == {"literal_in_bed", "intention_to_sleep"}
    with pytest.raises(Exception, match="tib_definition"):
        _reg().validate(_m3_sleep("behavioral.time_in_bed", 8.0))


def test_no_sleep_efficiency_without_time_in_bed():
    s = summarize("SIM-T01", [_m3_sleep("behavioral.sleep_duration", 6.0)])
    assert not [d for d in s.derived_values if d.name == "sleep_efficiency"]
