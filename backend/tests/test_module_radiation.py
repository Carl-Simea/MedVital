"""Radiation module tests. Imports only the radiation module and core (independence)."""

import pytest

from medvital.core.observation import ModuleId
from medvital.core.provenance import DataOrigin
from medvital.modules.radiation import MODULE
from medvital.modules.radiation.calculations import cumulative_dose
from medvital.modules.radiation.module import CUMULATIVE_DOSE, DOSE_RATE
from tests.conftest import make_obs


def rate(day: int, value: float, **kw):
    return make_obs(
        module=ModuleId.RADIATION, metric=DOSE_RATE, unit="uGy/day", value=value, day=day, **kw
    )


def test_cumulative_dose_is_trapezoidal_integral():
    assert cumulative_dose([0, 1, 2], [100, 100, 100]) == pytest.approx(200.0)
    assert cumulative_dose([0, 2], [0, 10]) == pytest.approx(10.0)


def test_derive_produces_modeled_cumulative_dose_with_provenance():
    inputs = [rate(0, 100.0), rate(1, 100.0), rate(2, 100.0)]
    (out,) = MODULE.derive(inputs)
    assert out.metric == CUMULATIVE_DOSE
    assert out.unit == "uGy"
    assert out.value == pytest.approx(200.0)
    assert out.provenance.origin is DataOrigin.MODELED
    assert set(out.provenance.derived_from) == {o.id for o in inputs}
    assert out.observed_at == inputs[-1].observed_at
    assert out.context["input_origin"] == "simulated"


def test_derive_needs_two_distinct_times_and_ignores_other_astronauts():
    assert MODULE.derive([rate(0, 100.0)]) == []
    assert MODULE.derive([rate(0, 100.0), rate(0, 90.0)]) == []
    mixed = [rate(0, 100.0), rate(1, 100.0), rate(0, 5.0, astronaut_id="SIM-002")]
    assert len(MODULE.derive(mixed)) == 1


def test_derive_is_deterministic():
    inputs = [rate(0, 100.0), rate(1, 110.0)]
    assert MODULE.derive(inputs)[0].id == MODULE.derive(list(reversed(inputs)))[0].id


def test_derived_metric_is_modeled_only():
    spec = MODULE.spec(CUMULATIVE_DOSE)
    assert spec is not None and spec.is_derived
