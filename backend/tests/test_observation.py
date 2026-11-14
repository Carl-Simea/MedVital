from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from medvital.core.observation import HealthObservation
from tests.conftest import make_obs, sim_provenance


def _payload(**overrides):
    base = {
        "id": str(uuid4()),
        "astronaut_id": "SIM-001",
        "module": "cardiovascular",
        "metric": "heart_rate",
        "value": 60.0,
        "unit": "bpm",
        "observed_at": "2030-01-01T00:00:00Z",
        "provenance": sim_provenance().model_dump(mode="json"),
    }
    base.update(overrides)
    return base


def test_valid_observation_round_trips_through_json():
    obs = make_obs()
    again = HealthObservation.model_validate_json(obs.model_dump_json())
    assert again == obs


def test_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        HealthObservation.model_validate(_payload(observed_at="2030-01-01T00:00:00"))


def test_timestamps_normalised_to_utc():
    local = timezone(timedelta(hours=-5))
    obs = HealthObservation.model_validate(_payload(observed_at="2030-01-01T00:00:00-05:00"))
    assert obs.observed_at.tzinfo is UTC
    assert obs.observed_at == datetime(2030, 1, 1, 5, tzinfo=UTC)
    assert obs.observed_at == datetime(2030, 1, 1, tzinfo=local)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_non_finite_values_rejected(bad):
    with pytest.raises(ValidationError):
        make_obs(value=bad)


def test_extra_fields_and_bad_ids_rejected():
    with pytest.raises(ValidationError):
        HealthObservation.model_validate(_payload(diagnosis="none"))
    with pytest.raises(ValidationError):
        HealthObservation.model_validate(_payload(astronaut_id="bad id!"))
    with pytest.raises(ValidationError):
        HealthObservation.model_validate(_payload(metric="Heart Rate"))
    with pytest.raises(ValidationError):
        HealthObservation.model_validate(_payload(schema_version=2))


def test_context_is_bounded():
    with pytest.raises(ValidationError):
        make_obs(context={f"k{i}": "v" for i in range(17)})
    with pytest.raises(ValidationError):
        make_obs(context={"k": "x" * 201})
