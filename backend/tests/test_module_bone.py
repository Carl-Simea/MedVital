"""Bone module tests. Imports only the bone module and core (independence)."""

import pytest

from medvital.core.observation import ModuleId
from medvital.modules.bone import MODULE
from medvital.modules.bone.calculations import percent_change
from medvital.modules.bone.module import BMD, BMD_CHANGE
from tests.conftest import make_obs


def bmd(day: int, value: float, site: str = "site_a", **kw):
    return make_obs(
        module=ModuleId.BONE,
        metric=BMD,
        unit="g/cm2",
        value=value,
        day=day,
        context={"site": site},
        **kw,
    )


def test_percent_change():
    assert percent_change(1.0, 0.9) == pytest.approx(-10.0)
    assert percent_change(2.0, 3.0) == pytest.approx(50.0)
    with pytest.raises(ValueError):
        percent_change(0.0, 1.0)


def test_derive_uses_first_and_last_per_site():
    inputs = [bmd(0, 1.0), bmd(30, 0.98), bmd(60, 0.95)]
    (out,) = MODULE.derive(inputs)
    assert out.metric == BMD_CHANGE
    assert out.value == pytest.approx(-5.0)
    assert out.context["site"] == "site_a"
    assert len(out.provenance.derived_from) == 2


def test_derive_keeps_sites_separate():
    inputs = [bmd(0, 1.0, "a"), bmd(30, 1.1, "a"), bmd(0, 2.0, "b"), bmd(30, 1.0, "b")]
    values = {o.context["site"]: o.value for o in MODULE.derive(inputs)}
    assert values == {"a": pytest.approx(10.0), "b": pytest.approx(-50.0)}


def test_derive_skips_single_observation_and_zero_baseline():
    assert MODULE.derive([bmd(0, 1.0)]) == []
    assert MODULE.derive([bmd(0, 0.0), bmd(30, 1.0)]) == []
