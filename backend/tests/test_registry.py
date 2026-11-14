from datetime import UTC, datetime
from uuid import uuid4

import pytest

from medvital.core.observation import HealthObservation, ModuleId
from medvital.core.provenance import DataOrigin, Provenance
from medvital.registry import MODULES, ObservationRejected, validate_observation
from tests.conftest import make_obs


def test_all_four_modules_registered():
    assert set(MODULES) == set(ModuleId)


def test_metric_names_are_unique_across_modules():
    names = [s.name for m in MODULES.values() for s in m.metrics]
    assert len(names) == len(set(names))


def test_valid_observation_accepted():
    validate_observation(make_obs())


def test_unknown_metric_rejected():
    with pytest.raises(ObservationRejected, match="not defined"):
        validate_observation(make_obs(metric="made_up_metric"))


def test_metric_from_wrong_module_rejected():
    with pytest.raises(ObservationRejected):
        validate_observation(make_obs(module=ModuleId.BONE, metric="heart_rate"))


def test_wrong_unit_rejected():
    with pytest.raises(ObservationRejected, match="unit"):
        validate_observation(make_obs(unit="kg"))


def test_derived_metric_cannot_be_submitted_as_simulated():
    with pytest.raises(ObservationRejected, match="origin"):
        validate_observation(
            make_obs(module=ModuleId.CARDIOVASCULAR, metric="mean_arterial_pressure", unit="mmHg")
        )


def test_base_metric_cannot_be_submitted_as_modeled():
    modeled = HealthObservation(
        id=uuid4(),
        astronaut_id="SIM-001",
        module=ModuleId.CARDIOVASCULAR,
        metric="heart_rate",
        value=60.0,
        unit="bpm",
        observed_at=datetime(2030, 1, 1, tzinfo=UTC),
        provenance=Provenance(
            origin=DataOrigin.MODELED, source="x", method="m", derived_from=(uuid4(),)
        ),
    )
    with pytest.raises(ObservationRejected, match="origin"):
        validate_observation(modeled)


def test_measured_data_is_accepted_only_with_a_citation():
    measured = make_obs(
        provenance=Provenance(origin=DataOrigin.MEASURED, source="inst", source_ref="ref-1")
    )
    validate_observation(measured)
