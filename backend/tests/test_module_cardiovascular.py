"""Cardiovascular module tests. Imports only the cardiovascular module and core."""

import pytest

from medvital.core.observation import ModuleId
from medvital.modules.cardiovascular import MODULE
from medvital.modules.cardiovascular.calculations import mean_arterial_pressure
from medvital.modules.cardiovascular.module import DIASTOLIC, MAP, SYSTOLIC
from tests.conftest import make_obs


def bp(metric: str, value: float, day: int = 0, **kw):
    return make_obs(
        module=ModuleId.CARDIOVASCULAR, metric=metric, unit="mmHg", value=value, day=day, **kw
    )


def test_mean_arterial_pressure_formula():
    assert mean_arterial_pressure(120.0, 80.0) == pytest.approx(80.0 + 40.0 / 3.0)
    with pytest.raises(ValueError):
        mean_arterial_pressure(70.0, 80.0)


def test_derive_pairs_systolic_and_diastolic_by_time():
    inputs = [bp(SYSTOLIC, 120.0, 0), bp(DIASTOLIC, 80.0, 0), bp(SYSTOLIC, 130.0, 1)]
    (out,) = MODULE.derive(inputs)
    assert out.metric == MAP
    assert out.value == pytest.approx(80.0 + 40.0 / 3.0)
    assert len(out.provenance.derived_from) == 2


def test_derive_ignores_impossible_pairs_and_other_astronauts():
    assert MODULE.derive([bp(SYSTOLIC, 70.0), bp(DIASTOLIC, 80.0)]) == []
    unpaired = [bp(SYSTOLIC, 120.0), bp(DIASTOLIC, 80.0, astronaut_id="SIM-002")]
    assert MODULE.derive(unpaired) == []


def test_heart_rate_has_no_derived_value():
    hr = make_obs(module=ModuleId.CARDIOVASCULAR, metric="heart_rate", unit="bpm", value=60.0)
    assert MODULE.derive([hr]) == []
