"""End-to-end, in-process: two simulated devices -> uplink -> gateway API -> SQLite -> live view.

Uses the real application, real SQLite file and real device code; only the HTTP hop is a
FastAPI TestClient instead of a socket (a real-socket run is documented in the README).
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from medvital.config import Settings
from medvital.device.simulator import WearableSimulator
from medvital.device.uplink import Uplink, UplinkError
from medvital.main import create_app

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
        assert not s["derived_values"] or module != "radiation"  # dose rates are never summed
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
