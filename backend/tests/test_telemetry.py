from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from medvital.core.schema import DataOrigin, ModuleId, Quality
from medvital.core.telemetry import TelemetryEvent, TelemetryStatus
from medvital.db.repository import InMemoryObservationRepository
from medvital.registry import build_registry
from medvital.telemetry import event_to_observation, ingest_telemetry, observation_id

NOW = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)  # arbitrary fixed test time


def make_event(**overrides) -> dict:
    """The briefing's example event plus the two synthetic-provenance extension fields."""
    event = {
        "event_id": "EVT-000001",
        "device_id": "MEDVITAL-WEARABLE-001",
        "crew_id": "CREW-001",
        "timestamp": "2030-01-01T11:59:59Z",
        "domain": "cardiovascular",
        "indicator": "heart_rate",
        "value": 88,
        "unit": "bpm",
        "source": "simulated_sensor",
        "quality": "valid",
        "synthetic": True,
        "generator_version": "test",
        "seed": 1,
    }
    event.update(overrides)
    return event


@pytest.fixture
def registry():
    return build_registry()


@pytest.fixture
def repo():
    return InMemoryObservationRepository()


def ingest(repo, registry, events, **kw):
    return ingest_telemetry(repo, registry, events, now=NOW, **kw)


class TestTelemetryEvent:
    def test_briefing_example_with_synthetic_extensions_is_valid(self):
        e = TelemetryEvent.model_validate(make_event())
        assert e.domain is ModuleId.CARDIOVASCULAR and e.synthetic is True

    def test_contract_has_the_eleven_briefing_fields(self):
        required = set(TelemetryEvent.model_json_schema()["required"])
        assert required == {
            "event_id", "device_id", "crew_id", "timestamp", "domain", "indicator",
            "value", "unit", "source", "quality", "synthetic",
        }  # fmt: skip

    def test_synthetic_requires_generator_and_seed(self):
        with pytest.raises(ValidationError, match="generator_version and seed"):
            TelemetryEvent.model_validate(make_event(seed=None))

    def test_measured_requires_source_ref(self):
        with pytest.raises(ValidationError, match="source_ref"):
            TelemetryEvent.model_validate(make_event(synthetic=False, generator_version=None, seed=None))

    def test_unknown_fields_forbidden(self):
        with pytest.raises(ValidationError):
            TelemetryEvent.model_validate(make_event(surprise=1))

    def test_naive_timestamp_and_nan_rejected(self):
        with pytest.raises(ValidationError):
            TelemetryEvent.model_validate(make_event(timestamp="2030-01-01T11:59:59"))
        with pytest.raises(ValidationError):
            TelemetryEvent.model_validate(make_event(value=float("nan")))

    def test_quality_values(self):
        assert {q.value for q in Quality} == {"valid", "suspect", "invalid"}


class TestMapping:
    def test_bpm_maps_to_canonical_metric_and_unit(self, registry):
        obs = event_to_observation(TelemetryEvent.model_validate(make_event()), registry)
        assert obs.metric == "cardiovascular.heart_rate" and obs.unit == "{beats}/min"
        assert obs.subject_id == "CREW-001" and obs.device_id == "MEDVITAL-WEARABLE-001"
        assert obs.provenance.data_origin is DataOrigin.SIMULATED and obs.provenance.seed == 1

    def test_observation_id_is_deterministic_per_device_and_event(self):
        assert observation_id("D1", "E1") == observation_id("D1", "E1")
        assert observation_id("D1", "E1") != observation_id("D2", "E1")

    def test_measured_event_is_labelled_measured(self, registry):
        e = TelemetryEvent.model_validate(
            make_event(synthetic=False, generator_version=None, seed=None, source_ref="test://sensor/1")
        )
        assert event_to_observation(e, registry).provenance.data_origin is DataOrigin.MEASURED


class TestIngest:
    def test_accepts_and_stores(self, repo, registry):
        r = ingest(repo, registry, [make_event()])
        assert (r.accepted, r.duplicate, r.rejected) == (1, 0, 0)
        assert r.results[0].status is TelemetryStatus.ACCEPTED and repo.head_seq() == 1

    def test_retry_is_duplicate_not_double_stored(self, repo, registry):
        ingest(repo, registry, [make_event()])
        r = ingest(repo, registry, [make_event()])
        assert r.duplicate == 1 and repo.head_seq() == 1

    def test_same_event_id_different_value_is_rejected_and_audited(self, repo, registry):
        ingest(repo, registry, [make_event(value=88)])
        r = ingest(repo, registry, [make_event(value=99)])
        assert r.rejected == 1 and "different content" in r.results[0].error
        assert repo.rejection_count() == 1 and repo.head_seq() == 1

    def test_malformed_event_is_rejected_audited_with_raw_payload(self, repo, registry):
        bad = make_event()
        del bad["quality"]
        r = ingest(repo, registry, [bad])
        assert r.rejected == 1 and "quality" in r.results[0].error
        (rec,) = repo.list_rejections()
        assert rec.payload["event_id"] == "EVT-000001" and rec.device_id == "MEDVITAL-WEARABLE-001"

    def test_non_dict_event_is_audited_not_crashing(self, repo, registry):
        r = ingest(repo, registry, ["not an object"])
        assert r.rejected == 1 and repo.rejection_count() == 1

    def test_unknown_indicator_and_wrong_unit_rejected(self, repo, registry):
        r = ingest(
            repo, registry,
            [make_event(event_id="E-1", indicator="made_up"), make_event(event_id="E-2", unit="furlongs")],
        )  # fmt: skip
        assert r.rejected == 2 and "unknown indicator" in r.results[0].error
        assert "not accepted" in r.results[1].error

    def test_negative_dose_rate_rejected_by_physical_rule(self, repo, registry):
        r = ingest(
            repo, registry,
            [make_event(domain="radiation", indicator="dose_rate", unit="uGy/h", value=-1)],
        )  # fmt: skip
        assert r.rejected == 1 and "negative" in r.results[0].error

    def test_future_timestamp_rejected_as_clock_skew(self, repo, registry):
        future = (NOW + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        r = ingest(repo, registry, [make_event(timestamp=future)])
        assert r.rejected == 1 and "future" in r.results[0].error

    def test_small_forward_skew_is_tolerated(self, repo, registry):
        near = (NOW + timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
        assert ingest(repo, registry, [make_event(timestamp=near)]).accepted == 1

    def test_suspect_quality_is_stored_not_dropped(self, repo, registry):
        r = ingest(repo, registry, [make_event(quality="suspect")])
        assert r.accepted == 1
        (o,) = repo.query()
        assert o.quality is Quality.SUSPECT

    def test_bad_event_does_not_block_the_rest(self, repo, registry):
        bad = make_event(event_id="E-bad", unit="furlongs")
        r = ingest(repo, registry, [make_event(event_id="E-1"), bad, make_event(event_id="E-2")])
        assert [x.status.value for x in r.results] == ["accepted", "rejected", "accepted"]
        assert repo.head_seq() == 2

    def test_every_event_gets_exactly_one_outcome(self, repo, registry):
        events = [make_event(event_id=f"E-{i}", value=60 + i) for i in range(5)] + ["junk"]
        r = ingest(repo, registry, events)
        assert len(r.results) == len(events) and r.accepted + r.duplicate + r.rejected == len(events)
