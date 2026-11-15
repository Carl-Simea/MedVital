"""Wearable telemetry: device simulator and uplink, gateway ingestion, end-to-end pipeline.

Merged from: test_telemetry.py, test_gateway_pipeline.py, test_device.py."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from medvital.config import Settings
from medvital.core.schema import DataOrigin, ModuleId, Quality
from medvital.core.telemetry import TelemetryEvent, TelemetryStatus
from medvital.db.repository import InMemoryObservationRepository
from medvital.device.simulator import GENERATOR_VERSION, WearableSimulator
from medvital.device.uplink import Uplink, UplinkError, run_device
from medvital.main import create_app
from medvital.registry import build_registry
from medvital.telemetry import event_to_observation, ingest_telemetry, observation_id

# ---------------------------------------------------------------------- from test_telemetry.py

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


# ---------------------------------------------------------------------- from test_gateway_pipeline.py

T0 = datetime.now(UTC) - timedelta(minutes=1)  # recent, so the gateway's future-skew guard is irrelevant


class ClientTransport:
    """Device-side transport that talks to the gateway through a TestClient."""

    def __init__(self, client: TestClient):
        self.client = client
        self.down = False

    def post_events(self, events):
        if self.down:
            raise UplinkError("network", "gateway unreachable")
        r = self.client.post("/api/v1/telemetry", json={"events": events})
        if r.status_code != 200:
            raise UplinkError("http", f"HTTP {r.status_code}", r.status_code)
        return r.json()


@pytest.fixture
def gateway(tmp_path):
    settings = Settings(repository="sqlite", sqlite_path=str(tmp_path / "gateway.db"))
    app = create_app(settings)
    with TestClient(app) as client:
        yield client, settings


def drive(sim, uplink, ticks, start=T0):
    for i in range(ticks):
        uplink.enqueue(sim.tick(start + timedelta(seconds=i)))


def test_two_devices_reach_the_dashboard_feed(gateway):
    client, _ = gateway
    transport = ClientTransport(client)
    sims = [
        (WearableSimulator("MEDVITAL-WEARABLE-001", "CREW-001", seed=1, start=T0, slow_every=5), Uplink(transport)),
        (WearableSimulator("MEDVITAL-WEARABLE-002", "CREW-002", seed=2, start=T0, slow_every=5), Uplink(transport)),
    ]
    for sim, uplink in sims:
        drive(sim, uplink, ticks=10)
        report = uplink.flush()
        assert report.error is None and report.rejected == 0

    live = client.get("/api/v1/live").json()
    assert [d["device_id"] for d in live["devices"]] == ["MEDVITAL-WEARABLE-001", "MEDVITAL-WEARABLE-002"]
    assert [d["crew_id"] for d in live["devices"]] == ["CREW-001", "CREW-002"]
    for device in live["devices"]:
        assert {r["domain"] for r in device["readings"]} == {"radiation", "bone", "cardiovascular", "behavioral"}
        assert all(r["data_origin"] == "simulated" and r["quality"] == "valid" for r in device["readings"])
    # 2 devices x (10 ticks x 2 + 2 slow ticks x 2)
    assert live["totals"] == {"observations_stored": 48, "rejected": 0}
    assert "not astronaut data" in live["notice"]


def test_modules_summarise_the_telemetry(gateway):
    client, _ = gateway
    uplink = Uplink(ClientTransport(client))
    drive(WearableSimulator("DEV-1", "CREW-001", seed=3, start=T0, slow_every=5), uplink, ticks=10)
    uplink.flush()
    metrics = {}
    for module in ("radiation", "bone", "cardiovascular", "behavioral"):
        s = client.get(f"/api/v1/modules/{module}/summary", params={"subject_id": "CREW-001"}).json()
        assert s["observation_count"] > 0
        metrics[module] = {m["metric"] for m in s["metric_summaries"]}
        assert all(m["data_origin"] == "simulated" for m in s["metric_summaries"])
        if module == "radiation":  # rates are never summed: only the labelled rate x time integration
            for d in s["derived_values"]:
                assert d["name"] == "integrated_dose_over_sampled_intervals" and d["unit"] == "uGy"
                assert d["data_origin"] == "modeled" and "piecewise-constant" in d["method"]
    assert "radiation.dose_rate" in metrics["radiation"]
    assert "cardiovascular.heart_rate" in metrics["cardiovascular"]
    assert "bone.countermeasure_exercise_duration" in metrics["bone"]
    assert "behavioral.sleep_duration" in metrics["behavioral"]


def test_gateway_outage_buffers_then_syncs_without_loss_or_duplicates(gateway):
    client, _ = gateway
    transport = ClientTransport(client)
    uplink = Uplink(transport)
    sim = WearableSimulator("DEV-1", "CREW-001", seed=4, start=T0, slow_every=1000)

    drive(sim, uplink, ticks=5)
    assert uplink.flush().error is None
    transport.down = True
    drive(sim, uplink, ticks=5, start=T0 + timedelta(seconds=5))
    assert uplink.flush().error is not None and len(uplink.buffer) == 10
    transport.down = False
    report = uplink.flush()
    assert report.error is None and report.accepted == 10 and not uplink.buffer
    # Retrying the identical batch is harmless.
    assert client.get("/api/v1/live").json()["totals"]["observations_stored"] == 5 * 2 + 5 * 2 + 2


def test_data_survives_a_gateway_restart(tmp_path):
    settings = Settings(repository="sqlite", sqlite_path=str(tmp_path / "gateway.db"))
    with TestClient(create_app(settings)) as first:
        uplink = Uplink(ClientTransport(first))
        drive(WearableSimulator("DEV-1", "CREW-001", seed=5, start=T0), uplink, ticks=3)
        uplink.flush()
        before = first.get("/api/v1/live").json()
    with TestClient(create_app(settings)) as second:  # new process-equivalent, same database file
        after = second.get("/api/v1/live").json()
    assert after["devices"] == before["devices"]
    assert after["totals"]["observations_stored"] == before["totals"]["observations_stored"] > 0


def test_bad_events_are_audited_and_visible(gateway):
    client, _ = gateway
    good = WearableSimulator("DEV-1", "CREW-001", seed=6, start=T0).tick(T0)
    bad = dict(good[0], event_id="EVT-BAD", unit="furlongs")
    r = client.post("/api/v1/telemetry", json={"events": [bad, *good]}).json()
    assert r["rejected"] == 1 and r["accepted"] == len(good)
    rejections = client.get("/api/v1/telemetry/rejections").json()
    assert len(rejections) == 1 and rejections[0]["payload"]["event_id"] == "EVT-BAD"
    assert "furlongs" in rejections[0]["reason"]
    assert client.get("/api/v1/live").json()["totals"]["rejected"] == 1


def test_telemetry_schema_endpoint_documents_the_contract(gateway):
    client, _ = gateway
    schema = client.get("/api/v1/telemetry/schema").json()
    assert {"event_id", "device_id", "crew_id", "timestamp", "domain", "indicator", "value", "unit",
            "source", "quality", "synthetic"} <= set(schema["required"])  # fmt: skip


def test_live_is_empty_before_any_device_connects(gateway):
    client, _ = gateway
    assert client.get("/api/v1/live").json()["devices"] == []


# ---------------------------------------------------------------------- from test_device.py

DEVICE_T0 = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


def sim(device_id="DEV-1", crew="CREW-001", seed=7, **kw):
    return WearableSimulator(device_id, crew, seed=seed, start=DEVICE_T0, **kw)


class TestSimulator:
    def test_events_satisfy_the_telemetry_contract_and_are_synthetic(self):
        events = sim(slow_every=1).tick(DEVICE_T0)
        for e in events:
            parsed = TelemetryEvent.model_validate(e)
            assert parsed.synthetic is True and parsed.source == "simulated_sensor"
            assert parsed.generator_version == GENERATOR_VERSION and parsed.seed == 7

    def test_all_four_domains_appear(self):
        events = sim(slow_every=1).tick(DEVICE_T0)
        assert {e["domain"] for e in events} == {"radiation", "bone", "cardiovascular", "behavioral"}

    def test_slow_indicators_only_every_n_ticks(self):
        s = sim(slow_every=3)
        counts = [len(s.tick(DEVICE_T0 + timedelta(seconds=i))) for i in range(6)]
        assert counts == [4, 2, 2, 4, 2, 2]

    def test_deterministic_for_same_seed(self):
        a, b = sim(), sim()
        assert [a.tick(DEVICE_T0 + timedelta(seconds=i)) for i in range(5)] == [
            b.tick(DEVICE_T0 + timedelta(seconds=i)) for i in range(5)
        ]

    def test_event_ids_unique_within_a_run(self):
        s = sim(slow_every=1)
        ids = [e["event_id"] for i in range(20) for e in s.tick(DEVICE_T0 + timedelta(seconds=i))]
        assert len(ids) == len(set(ids))

    def test_restart_uses_a_different_session_prefix(self):
        a = WearableSimulator("DEV-1", "CREW-001", start=DEVICE_T0).tick(DEVICE_T0)[0]["event_id"]
        b = WearableSimulator("DEV-1", "CREW-001", start=DEVICE_T0 + timedelta(seconds=5)).tick(DEVICE_T0)[0]["event_id"]
        assert a != b

    def test_radiation_scenario_factor_scales_dose_rate(self):
        base, boosted = sim(), sim()
        boosted.radiation_factor = 10.0
        dose = lambda s: next(e for e in s.tick(DEVICE_T0) if e["indicator"] == "dose_rate")["value"]  # noqa: E731
        assert dose(boosted) == pytest.approx(dose(base) * 10, abs=0.1)  # values are rounded to 2 dp

    def test_two_crew_profiles_differ(self):
        a = sim(crew="CREW-001").tick(DEVICE_T0)[0]["value"]
        b = sim(crew="CREW-002").tick(DEVICE_T0)[0]["value"]
        assert abs(a - b) > 3  # arbitrary profile centres differ by 10 bpm


class FakeTransport:
    """Stands in for the gateway. Fails while ``down``; otherwise accepts everything once."""

    def __init__(self):
        self.down = False
        self.received: list[dict] = []
        self.verdicts: dict[str, str] = {}  # event_id -> forced status

    def post_events(self, events):
        if self.down:
            raise UplinkError("network", "connection refused")
        results = []
        for e in events:
            status = self.verdicts.get(e["event_id"])
            if status is None:
                seen = {x["event_id"] for x in self.received}
                status = "duplicate" if e["event_id"] in seen else "accepted"
            if status != "rejected":
                self.received.append(e)
            results.append({"event_id": e["event_id"], "status": status, "error": "bad" if status == "rejected" else None})
        return {"results": results}


def evs(n, start=0):
    return [{"event_id": f"E-{i}"} for i in range(start, start + n)]


class TestUplink:
    def test_delivers_and_empties_buffer(self):
        t = FakeTransport()
        u = Uplink(t)
        u.enqueue(evs(5))
        r = u.flush()
        assert (r.sent, r.accepted, r.error) == (5, 5, None) and not u.buffer

    def test_offline_keeps_events_in_order_then_drains_without_loss_or_duplicates(self):
        t = FakeTransport()
        u = Uplink(t, batch_size=2)
        t.down = True
        u.enqueue(evs(5))
        assert u.flush().error is not None and len(u.buffer) == 5
        u.enqueue(evs(2, start=5))
        t.down = False
        r = u.flush()
        assert r.error is None and not u.buffer and r.accepted == 7
        assert [e["event_id"] for e in t.received] == [f"E-{i}" for i in range(7)]

    def test_rejected_verdict_is_final_and_counted(self):
        t = FakeTransport()
        u = Uplink(t)
        t.verdicts["E-1"] = "rejected"
        u.enqueue(evs(3))
        r = u.flush()
        assert (r.accepted, r.rejected) == (2, 1) and not u.buffer
        assert "E-1" in u.rejected_reasons[0]

    def test_whole_request_4xx_is_dropped_and_counted_not_looped(self):
        class Refusing:
            def post_events(self, events):
                raise UplinkError("http", "HTTP 422", 422)

        u = Uplink(Refusing())
        u.enqueue(evs(3))
        r = u.flush()
        assert r.rejected == 3 and not u.buffer and r.error is None

    def test_5xx_keeps_events(self):
        class Broken:
            def post_events(self, events):
                raise UplinkError("http", "HTTP 503", 503)

        u = Uplink(Broken())
        u.enqueue(evs(3))
        assert u.flush().error and len(u.buffer) == 3

    def test_overflow_drops_oldest_and_says_so(self):
        u = Uplink(FakeTransport(), max_buffer=3)
        u.enqueue(evs(5))
        assert u.dropped == 2 and [e["event_id"] for e in u.buffer] == ["E-2", "E-3", "E-4"]


class TestRunDevice:
    def test_outage_then_recovery_delivers_everything_exactly_once(self):
        t = FakeTransport()
        u = Uplink(t)
        s = sim(slow_every=1000)
        now = [DEVICE_T0]
        logs: list[str] = []

        def sleep(seconds):
            now[0] += timedelta(seconds=seconds)
            if now[0] >= DEVICE_T0 + timedelta(seconds=5):  # gateway comes back after 5 s
                t.down = False

        t.down = True
        run_device(s, u, interval=1.0, duration=12, clock=lambda: now[0], sleep=sleep, log=logs.append)
        ids = [e["event_id"] for e in t.received]
        # 12 ticks x (heart_rate, dose_rate) + the sleep/exercise pair emitted on the very first tick
        assert len(ids) == len(set(ids)) and len(ids) == 12 * 2 + 2
        assert not u.buffer
        assert any("UNREACHABLE" in line for line in logs) and any("reachable; buffer drained" in line for line in logs)
