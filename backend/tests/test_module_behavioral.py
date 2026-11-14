"""Behavioral module tests. Imports only the behavioral module and core."""

import pytest

from medvital.core.observation import ModuleId
from medvital.modules.behavioral import MODULE
from medvital.modules.behavioral.calculations import trailing_mean
from medvital.modules.behavioral.module import SLEEP, SLEEP_MEAN
from tests.conftest import make_obs


def sleep(day: int, value: float, **kw):
    return make_obs(module=ModuleId.BEHAVIORAL, metric=SLEEP, unit="h", value=value, day=day, **kw)


def test_trailing_mean():
    assert trailing_mean([1, 2, 3, 4, 5], 3) == pytest.approx(4.0)
    with pytest.raises(ValueError):
        trailing_mean([1, 2], 3)
    with pytest.raises(ValueError):
        trailing_mean([1, 2], 0)


def test_derive_uses_last_seven_samples():
    inputs = [sleep(d, float(d)) for d in range(10)]  # values 0..9; last seven are 3..9
    (out,) = MODULE.derive(inputs)
    assert out.metric == SLEEP_MEAN
    assert out.value == pytest.approx(6.0)
    assert out.observed_at == inputs[-1].observed_at
    assert set(out.provenance.derived_from) == {o.id for o in inputs[-7:]}


def test_derive_needs_seven_samples():
    assert MODULE.derive([sleep(d, 7.0) for d in range(6)]) == []


def test_stress_scale_is_bounded_placeholder():
    spec = MODULE.spec("self_reported_stress")
    assert spec is not None
    assert (spec.physical_min, spec.physical_max) == (0.0, 10.0)
    assert spec.unit == "score_0_10"
