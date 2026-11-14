from datetime import UTC, datetime, timedelta

import pytest

from medvital.core.telemetry import TelemetryEvent
from medvital.device.simulator import GENERATOR_VERSION, WearableSimulator
from medvital.device.uplink import Uplink, UplinkError, run_device

T0 = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


def sim(device_id="DEV-1", crew="CREW-001", seed=7, **kw):
    return WearableSimulator(device_id, crew, seed=seed, start=T0, **kw)


class TestSimulator:
    def test_events_satisfy_the_telemetry_contract_and_are_synthetic(self):
        events = sim(slow_every=1).tick(T0)
        for e in events:
            parsed = TelemetryEvent.model_validate(e)
            assert parsed.synthetic is True and parsed.source == "simulated_sensor"
            assert parsed.generator_version == GENERATOR_VERSION and parsed.seed == 7

    def test_all_four_domains_appear(self):
        events = sim(slow_every=1).tick(T0)
        assert {e["domain"] for e in events} == {"radiation", "bone", "cardiovascular", "behavioral"}

    def test_slow_indicators_only_every_n_ticks(self):
        s = sim(slow_every=3)
        counts = [len(s.tick(T0 + timedelta(seconds=i))) for i in range(6)]
        assert counts == [4, 2, 2, 4, 2, 2]

    def test_deterministic_for_same_seed(self):
        a, b = sim(), sim()
        assert [a.tick(T0 + timedelta(seconds=i)) for i in range(5)] == [
            b.tick(T0 + timedelta(seconds=i)) for i in range(5)
        ]

    def test_event_ids_unique_within_a_run(self):
        s = sim(slow_every=1)
        ids = [e["event_id"] for i in range(20) for e in s.tick(T0 + timedelta(seconds=i))]
        assert len(ids) == len(set(ids))

    def test_restart_uses_a_different_session_prefix(self):
        a = WearableSimulator("DEV-1", "CREW-001", start=T0).tick(T0)[0]["event_id"]
        b = WearableSimulator("DEV-1", "CREW-001", start=T0 + timedelta(seconds=5)).tick(T0)[0]["event_id"]
        assert a != b

    def test_radiation_scenario_factor_scales_dose_rate(self):
        base, boosted = sim(), sim()
        boosted.radiation_factor = 10.0
        dose = lambda s: next(e for e in s.tick(T0) if e["indicator"] == "dose_rate")["value"]  # noqa: E731
        assert dose(boosted) == pytest.approx(dose(base) * 10, abs=0.1)  # values are rounded to 2 dp

    def test_two_crew_profiles_differ(self):
        a = sim(crew="CREW-001").tick(T0)[0]["value"]
        b = sim(crew="CREW-002").tick(T0)[0]["value"]
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
        now = [T0]
        logs: list[str] = []

        def sleep(seconds):
            now[0] += timedelta(seconds=seconds)
            if now[0] >= T0 + timedelta(seconds=5):  # gateway comes back after 5 s
                t.down = False

        t.down = True
        run_device(s, u, interval=1.0, duration=12, clock=lambda: now[0], sleep=sleep, log=logs.append)
        ids = [e["event_id"] for e in t.received]
        # 12 ticks x (heart_rate, dose_rate) + the sleep/exercise pair emitted on the very first tick
        assert len(ids) == len(set(ids)) and len(ids) == 12 * 2 + 2
        assert not u.buffer
        assert any("UNREACHABLE" in line for line in logs) and any("reachable; buffer drained" in line for line in logs)
