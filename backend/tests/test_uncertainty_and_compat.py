"""M3: observation uncertainty field and schema-compatibility guarantees."""

import hashlib
import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from conftest import make_obs
from medvital.analysis import analyze
from medvital.core.schema import SCHEMA_VERSION, HealthObservation
from medvital.core.telemetry import TelemetryEvent
from medvital.db.repository import AddStatus
from medvital.db.sqlite import SqliteObservationRepository
from medvital.registry import build_registry
from medvital.telemetry import event_to_observation

SLEEP = "behavioral.sleep_duration"


def test_uncertainty_defaults_to_unknown_not_zero():
    o = make_obs(SLEEP, 7.0)
    assert o.uncertainty is None
    assert make_obs(SLEEP, 7.0).model_copy(update={"uncertainty": 0.0}).uncertainty == 0.0


@pytest.mark.parametrize("bad", [-0.1, float("nan"), float("inf")])
def test_uncertainty_must_be_finite_and_non_negative(bad):
    payload = make_obs(SLEEP, 7.0).model_dump(mode="json")
    payload["uncertainty"] = bad
    with pytest.raises(ValidationError):
        HealthObservation.model_validate(payload)


def test_schema_version_unchanged_and_legacy_payload_accepted():
    payload = make_obs(SLEEP, 7.0).model_dump(mode="json")
    del payload["uncertainty"]  # a v1 client that predates the field
    assert SCHEMA_VERSION == 1
    assert HealthObservation.model_validate(payload).uncertainty is None


def _legacy_fingerprint(o: HealthObservation) -> str:
    """Fingerprint as the previous model version computed it (no `uncertainty` key)."""
    payload = o.model_dump(mode="json")
    del payload["uncertainty"]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_sqlite_retry_of_pre_upgrade_row_is_duplicate_not_conflict(tmp_path):
    """Regression: an additive field must not turn a legitimate retry into a false conflict."""
    o = make_obs(SLEEP, 7.0)
    repo = SqliteObservationRepository(tmp_path / "gateway.db")
    legacy_payload = o.model_dump(mode="json")
    del legacy_payload["uncertainty"]
    repo._conn.execute(  # simulate a row written by the previous release
        "INSERT INTO observations (id, fingerprint, subject_id, module, metric, device_id, data_origin, "
        "observed_at, received_at, payload) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            str(o.id),
            _legacy_fingerprint(o),
            o.subject_id,
            o.module.value,
            o.metric,
            None,
            o.provenance.data_origin.value,
            "2030-01-01T00:00:00.000000Z",
            "2030-01-01T00:00:00.000000Z",
            json.dumps(legacy_payload),
        ),
    )
    assert repo.add(o).status is AddStatus.DUPLICATE
    assert repo.add(o.model_copy(update={"uncertainty": 0.2})).status is AddStatus.CONFLICT
    repo.close()


def test_telemetry_passes_uncertainty_through():
    ev = TelemetryEvent(
        event_id="EVT-1",
        device_id="W1",
        crew_id="SIM-T01",
        timestamp=datetime(2030, 1, 1, tzinfo=UTC),
        domain="cardiovascular",
        indicator="heart_rate",
        value=60.0,
        unit="bpm",
        source="pytest",
        quality="valid",
        synthetic=True,
        generator_version="t",
        seed=1,
        uncertainty=2.0,
    )
    assert event_to_observation(ev, build_registry()).uncertainty == 2.0


def test_analysis_reports_uncertainty_without_inventing_it():
    obs = [make_obs(SLEEP, v, day=i) for i, v in enumerate([1, 2, 3, 4, 5, 6, 9])]
    obs[-1] = obs[-1].model_copy(update={"uncertainty": 0.5})
    from medvital.analysis import AnalysisConfig, BaselineSpec

    (s,) = analyze(obs, AnalysisConfig(baseline=BaselineSpec(n=5), include_point_deviations=True)).series
    assert s.quality.uncertainty_known_count == 1
    assert [d.uncertainty for d in s.deviations] == [None, 0.5]  # unknown stays None
    assert s.anomalies[0].uncertainty == 0.5
