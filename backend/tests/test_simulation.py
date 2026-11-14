from datetime import UTC, datetime

import pytest

from medvital.core.schema import DataOrigin, ModuleId
from medvital.registry import build_registry
from medvital.simulation.generator import generate_observations
from medvital.simulation.profiles import SIMULATED_PROFILES, get_profile

START = datetime(2030, 1, 1, tzinfo=UTC)
PROFILE = SIMULATED_PROFILES[0]


def test_four_profiles_all_flagged_simulated():
    assert len(SIMULATED_PROFILES) == 4
    assert len({p.profile_id for p in SIMULATED_PROFILES}) == 4
    for p in SIMULATED_PROFILES:
        assert p.data_origin is DataOrigin.SIMULATED
        assert "not derived from any NASA dataset" in p.disclaimer


def test_get_profile():
    assert get_profile("SIM-A01") is SIMULATED_PROFILES[0]
    assert get_profile("nope") is None


def test_every_observation_is_simulated_with_seed():
    obs = generate_observations(PROFILE, START, days=15, seed=42)
    assert obs
    for o in obs:
        assert o.provenance.data_origin is DataOrigin.SIMULATED
        assert o.provenance.seed == 42
        assert o.provenance.generator_version


def test_deterministic_including_ids():
    a = generate_observations(PROFILE, START, days=10, seed=7)
    b = generate_observations(PROFILE, START, days=10, seed=7)
    assert [o.model_dump_json() for o in a] == [o.model_dump_json() for o in b]


def test_seed_changes_values_and_ids():
    a = generate_observations(PROFILE, START, days=10, seed=1)
    b = generate_observations(PROFILE, START, days=10, seed=2)
    assert {o.id for o in a}.isdisjoint({o.id for o in b})
    assert [o.value for o in a] != [o.value for o in b]


def test_ids_unique():
    obs = generate_observations(PROFILE, START, days=30, seed=3)
    assert len({o.id for o in obs}) == len(obs)


def test_covers_all_four_modules():
    obs = generate_observations(PROFILE, START, days=15, seed=0)
    assert {o.module for o in obs} == set(ModuleId)


def test_all_pass_registry_validation():
    registry = build_registry()
    for o in generate_observations(PROFILE, START, days=15, seed=0):
        registry.validate(o)


@pytest.mark.parametrize("days", [0, 731])
def test_days_bounds(days):
    with pytest.raises(ValueError):
        generate_observations(PROFILE, START, days=days, seed=0)


def test_requires_aware_start():
    with pytest.raises(ValueError):
        generate_observations(PROFILE, datetime(2030, 1, 1), days=1, seed=0)


def test_each_module_summarises_generated_data():
    registry = build_registry()
    obs = generate_observations(PROFILE, START, days=60, seed=5)
    for spec in registry.modules():
        s = spec.summarize(PROFILE.profile_id, obs)
        assert s.observation_count > 0
        assert s.derived_values, f"{spec.module_id} produced no derived values"
        assert all(d.input_origin is DataOrigin.SIMULATED for d in s.derived_values)
