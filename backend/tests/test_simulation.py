from datetime import datetime

import pytest

from medvital.core.provenance import DataOrigin
from medvital.core.simulation import SIM_METHOD
from medvital.registry import MODULES
from medvital.simulated_profiles import PROFILES

PROFILE = PROFILES["SIM-001"]


def test_every_profile_defines_every_base_metric():
    base = {s.name for m in MODULES.values() for s in m.metrics if not s.is_derived}
    for profile in PROFILES.values():
        assert base <= set(profile.parameters), profile.profile_id


def test_profiles_assume_no_drift():
    for profile in PROFILES.values():
        assert all(p.drift_per_day == 0.0 for p in profile.parameters.values())


@pytest.mark.parametrize("module", list(MODULES.values()), ids=lambda m: m.id.value)
def test_simulation_is_reproducible_and_labelled_simulated(module, t0):
    a = module.simulate(PROFILE, t0, 20, seed=5)
    b = module.simulate(PROFILE, t0, 20, seed=5)
    assert a == b
    assert a, "module produced no observations"
    for obs in a:
        assert obs.provenance.origin is DataOrigin.SIMULATED
        assert obs.provenance.seed == 5
        assert obs.provenance.method == SIM_METHOD
        assert obs.astronaut_id == PROFILE.profile_id


def test_different_seeds_and_profiles_differ(t0):
    cardio = [m for m in MODULES.values() if m.id.value == "cardiovascular"][0]
    a = cardio.simulate(PROFILE, t0, 10, seed=1)
    b = cardio.simulate(PROFILE, t0, 10, seed=2)
    c = cardio.simulate(PROFILES["SIM-002"], t0, 10, seed=1)
    assert [o.value for o in a] != [o.value for o in b]
    assert [o.value for o in a] != [o.value for o in c]


def test_ids_are_unique_and_stable(t0):
    cardio = [m for m in MODULES.values() if m.id.value == "cardiovascular"][0]
    obs = cardio.simulate(PROFILE, t0, 15, seed=9)
    assert len({o.id for o in obs}) == len(obs)
    assert [o.id for o in obs] == [o.id for o in cardio.simulate(PROFILE, t0, 15, seed=9)]


def test_physical_bounds_respected(t0):
    behavioral = [m for m in MODULES.values() if m.id.value == "behavioral"][0]
    for obs in behavioral.simulate(PROFILE, t0, 200, seed=3):
        spec = behavioral.spec(obs.metric)
        assert spec is not None
        if spec.physical_min is not None:
            assert obs.value >= spec.physical_min
        if spec.physical_max is not None:
            assert obs.value <= spec.physical_max


def test_cadence_is_respected(t0):
    bone = [m for m in MODULES.values() if m.id.value == "bone"][0]
    obs = bone.simulate(PROFILE, t0, 91, seed=1)
    assert [(o.observed_at - t0).days for o in obs] == [0, 30, 60, 90]


def test_naive_start_and_bad_days_rejected():
    cardio = [m for m in MODULES.values() if m.id.value == "cardiovascular"][0]
    with pytest.raises(ValueError):
        cardio.simulate(PROFILE, datetime(2030, 1, 1), 5, seed=1)
