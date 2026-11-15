"""Schema, API contract, configuration, uncertainty and backward compatibility.

Merged from: test_contract_and_config.py, test_schema.py, test_uncertainty_and_compat.py."""

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from conftest import make_obs, measured_provenance, simulated_provenance
from medvital.analysis import analyze
from medvital.config import Settings
from medvital.core.schema import (
    SCHEMA_VERSION,
    DataOrigin,
    HealthObservation,
    ModuleId,
    Provenance,
    observation_fingerprint,
)
from medvital.core.telemetry import TelemetryEvent
from medvital.db.factory import build_repository
from medvital.db.repository import AddStatus
from medvital.db.sqlite import SqliteObservationRepository
from medvital.registry import build_registry
from medvital.telemetry import event_to_observation

# ---------------------------------------------------------------------- from test_contract_and_config.py

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_openapi.py"


def test_committed_openapi_matches_code():
    """docs/api/openapi.json is the API contract; regenerate it when routes change."""
    result = subprocess.run([sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_postgres_requires_url():
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        build_repository(Settings(repository="postgres"))


def test_postgres_is_explicitly_not_implemented():
    with pytest.raises(NotImplementedError):
        build_repository(Settings(repository="postgres", database_url="postgresql://x"))


def test_unknown_repository():
    with pytest.raises(RuntimeError):
        build_repository(Settings(repository="mongo"))


def test_schema_sql_ships_with_package():
    from importlib.resources import files

    sql = (files("medvital.db") / "schema.sql").read_text(encoding="utf-8")
    assert "append-only" in sql and "data_origin" in sql


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("MEDVITAL_CORS_ORIGINS", "http://a.test, http://b.test")
    monkeypatch.setenv("MEDVITAL_REPOSITORY", "MEMORY")
    s = Settings.from_env()
    assert s.cors_origins == ("http://a.test", "http://b.test") and s.repository == "memory"


# ---------------------------------------------------------------------- from test_schema.py

class TestProvenance:
    def test_simulated_requires_generator_and_seed(self):
        with pytest.raises(ValidationError):
            Provenance(data_origin=DataOrigin.SIMULATED, source="x")
        with pytest.raises(ValidationError):
            Provenance(data_origin=DataOrigin.SIMULATED, source="x", generator_version="1")

    def test_measured_requires_source_ref(self):
        with pytest.raises(ValidationError, match="source_ref"):
            Provenance(data_origin=DataOrigin.MEASURED, source="x")

    def test_measured_rejects_generator_fields(self):
        with pytest.raises(ValidationError):
            Provenance(
                data_origin=DataOrigin.MEASURED, source="x", source_ref="r", generator_version="1", seed=1
            )

    def test_modeled_requires_method(self):
        with pytest.raises(ValidationError, match="method"):
            Provenance(data_origin=DataOrigin.MODELED, source="x")
        assert Provenance(data_origin=DataOrigin.MODELED, source="x", method="m v1")

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            Provenance(
                data_origin=DataOrigin.MODELED, source="x", method="m", surprise=1
            )  # type: ignore[call-arg]


class TestHealthObservation:
    def test_valid(self):
        obs = make_obs()
        assert obs.module is ModuleId.RADIATION
        assert obs.provenance.data_origin is DataOrigin.SIMULATED

    def test_metric_must_match_module(self):
        with pytest.raises(ValidationError, match="does not belong"):
            make_obs("radiation.absorbed_dose_daily", module=ModuleId.BONE)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_rejects_non_finite(self, bad):
        with pytest.raises(ValidationError):
            make_obs(value=bad)

    def test_rejects_naive_datetime(self):
        data = make_obs().model_dump()
        data["observed_at"] = datetime(2030, 1, 1)
        with pytest.raises(ValidationError):
            HealthObservation(**data)

    def test_normalises_to_utc(self):
        data = make_obs().model_dump()
        data["observed_at"] = datetime(2030, 1, 1, 5, tzinfo=timezone(timedelta(hours=5)))
        obs = HealthObservation(**data)
        assert obs.observed_at == datetime(2030, 1, 1, 0, tzinfo=UTC)
        assert obs.observed_at.utcoffset() == timedelta(0)

    def test_provenance_is_mandatory(self):
        data = make_obs().model_dump()
        del data["provenance"]
        with pytest.raises(ValidationError):
            HealthObservation(**data)

    def test_cannot_supersede_self(self):
        data = make_obs().model_dump()
        data["supersedes"] = data["id"]
        with pytest.raises(ValidationError, match="supersede"):
            HealthObservation(**data)

    def test_unsupported_schema_version(self):
        data = make_obs().model_dump()
        data["schema_version"] = 99
        with pytest.raises(ValidationError):
            HealthObservation(**data)

    def test_context_key_format(self):
        with pytest.raises(ValidationError):
            make_obs(context={"Bad Key": "x"})

    def test_subject_id_charset(self):
        with pytest.raises(ValidationError):
            make_obs(subject_id="has space")

    def test_is_immutable(self):
        obs = make_obs()
        with pytest.raises(ValidationError):
            obs.value = 2.0  # type: ignore[misc]


class TestFingerprint:
    def test_stable_and_roundtrip(self):
        obs = make_obs()
        again = HealthObservation.model_validate_json(obs.model_dump_json())
        assert observation_fingerprint(obs) == observation_fingerprint(again)

    def test_changes_with_content(self):
        i = uuid4()
        a = make_obs(value=1.0, id=i)
        b = make_obs(value=1.5, id=i)
        assert observation_fingerprint(a) != observation_fingerprint(b)

    def test_origin_changes_fingerprint(self):
        i = uuid4()
        a = make_obs(id=i, provenance=simulated_provenance())
        b = make_obs(id=i, provenance=measured_provenance())
        assert observation_fingerprint(a) != observation_fingerprint(b)


# ---------------------------------------------------------------------- from test_uncertainty_and_compat.py

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
