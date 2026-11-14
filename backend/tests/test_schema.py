from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from conftest import make_obs, measured_provenance, simulated_provenance
from medvital.core.schema import (
    DataOrigin,
    HealthObservation,
    ModuleId,
    Provenance,
    observation_fingerprint,
)


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
