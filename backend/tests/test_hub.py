"""Spacecraft hub: private network, double-check, alert rules, simulator, schedule, day-end sync, sign-up."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from medvital.hub import mission as M
from medvital.hub import rules
from medvital.hub import settings as S
from medvital.hub.app import create_hub_app

DAY10_EVA = 9 * 1440 + 13 * 60  # mission day 10, 13:00: first surface spacewalk, during the real May 2024 SEP


class FakeNasa:
    """Stands in for nasa/app.py: saves records by id, refuses everything while the link is down."""

    def __init__(self) -> None:
        self.up = True
        self.saved: dict[str, dict] = {}

    def __call__(self, method, path, body=None, timeout=5.0):
        if path == "/link":
            if method == "POST":
                self.up = bool(body["up"])
            return 200, {"up": self.up}
        if path == "/stats":
            by_a: dict[str, int] = {}
            for r in self.saved.values():
                by_a[r["astronautId"]] = by_a.get(r["astronautId"], 0) + 1
            return 200, {"total": len(self.saved), "by_astronaut": by_a}
        if path == "/batch":
            if not self.up:
                return 503, {"error": "link down"}
            for r in body["records"]:
                self.saved[r["id"]] = r
            return 200, {"saved": [r["id"] for r in body["records"]]}
        return 404, None


@pytest.fixture
def env(tmp_path):
    app = create_hub_app(data_dir=tmp_path, nasa_url="http://nasa.test", start_background=False)
    hub = app.state.hub
    nasa = FakeNasa()
    hub._nasa = nasa
    client = TestClient(app)
    keys = {a["id"]: a["device_key"] for a in hub.store.astronauts()}
    yield client, hub, nasa, keys
    hub.store.close()


class Wearable:
    def __init__(self, client, key, aid="astro-1", m=600.0):
        self.client, self.key, self.aid, self.seq, self.total, self.m = client, key, aid, 0, 0.0, m

    def send(self, hr=62, spo2=98, state="awake", dose=26.7, key=None):
        self.seq += 1
        self.m += S.MISSION_MINUTES_PER_BURST
        self.total += dose * S.MISSION_MINUTES_PER_BURST / 60 / 1000
        return self.client.post(
            "/hub/burst",
            json={
                "astronautId": self.aid,
                "deviceKey": key or self.key,
                "seq": self.seq,
                "missionMinute": self.m,
                "time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "heartRate": hr,
                "spo2": spo2,
                "state": state,
                "doseRate": dose,
                "totalDose": round(self.total, 5),
            },
        )


def test_mission_starts_with_crew_reports_and_schedule(env):
    client, hub, _, _ = env
    crew = client.get("/hub/astronauts").json()
    assert [a["id"] for a in crew] == ["astro-1", "astro-2", "astro-3", "astro-4"] and all(
        a["hasReport"] for a in crew
    )
    assert "Resting heart rate: 58 bpm" in client.get("/hub/astronauts/astro-1/report").text
    kinds = {e["kind"] for e in hub.store.all("SELECT DISTINCT kind FROM events")}
    assert {"sleep", "exercise", "test", "eva", "landing", "blackout", "space_weather"} <= kinds
    values = client.get("/hub/body/astro-1").json()["values"]
    assert (
        values["hr.rest"] == 58 and values["bp.sys"] == 112 and values["bmd.hipPct"] == 0
    )  # pre-flight report


def test_private_network_blocks_wrong_key(env):
    client, hub, _, keys = env
    w = Wearable(client, keys["astro-1"])
    assert w.send(key="stolen").status_code == 401
    assert hub.store.scalar("SELECT COUNT(*) FROM bursts") == 0
    assert "stolen" not in hub.store.one("SELECT payload FROM rejected")["payload"]  # the key is never stored


def test_glitch_is_flagged_not_alerted(env):
    client, _, _, keys = env
    w = Wearable(client, keys["astro-1"])
    w.send()
    r = w.send(hr=240).json()
    assert r["quality"] == "invalid" and r["alert"] is None


def test_heart_rate_alert_needs_confirmation_and_adapts_to_each_baseline(env):
    client, _, _, keys = env
    a1, a4 = (
        Wearable(client, keys["astro-1"]),
        Wearable(client, keys["astro-4"], "astro-4"),
    )  # baselines 58 / 72
    got1, got4 = [], []
    for _ in range(3):  # 105 bpm is high for astro-1 (ceiling 98) but fine for astro-4 (ceiling 112)
        got1.append(a1.send(hr=105).json()["alert"])
        got4.append(a4.send(hr=105).json()["alert"])
    assert got1[0] is None and "CHECK_VITALS" in got1  # the first high reading only waits for confirmation
    assert set(got4) == {None}


def test_solar_event_sends_spacewalker_back_and_resolves_inside(env):
    client, hub, _, keys = env
    w = Wearable(client, keys["astro-1"])
    w.send(state="spacewalk", dose=53)
    client.post("/hub/space-weather/replay")
    r = w.send(state="spacewalk", dose=1000).json()
    assert r["alert"] == "RETURN_NOW" and r["spaceWeather"]["solarEventActive"]
    assert w.send(state="spacewalk", dose=1000).json()["alert"] == "RETURN_NOW"  # repeats until inside
    assert w.send(state="awake").json()["alert"] is None
    assert hub.store.one("SELECT status FROM alerts WHERE code='RETURN_NOW'")["status"] == "resolved"


def test_real_sep_during_the_first_spacewalk_triggers_return_now(env):
    """The real 2024-05 DONKI SEP falls on mission day 10, during the planned EVA of astro-1 and astro-2."""
    _, hub, _, _ = env
    assert M.sep_active(DAY10_EVA) is not None
    hub.sim.tick(DAY10_EVA - 24)
    hub.sim.tick(DAY10_EVA)
    eva = hub.store.recent_bursts("astro-1", 1)[0]
    assert eva["state"] == "spacewalk"
    assert hub.store.one("SELECT * FROM alerts WHERE astronaut_id='astro-1' AND code='RETURN_NOW'")
    assert hub.store.recent_bursts("astro-3", 1)[0]["state"] != "spacewalk"  # not on this EVA


def test_rad_is_real_data_on_the_mission_timeline():
    cruise, surface = M.rad_at(600), M.rad_at(20 * 1440 + 600)
    assert cruise.phase == "cruise" and surface.phase == "surface"
    if S.RAD_FILE.exists():
        assert cruise.source.startswith("RAD RAD_RDR_2011") and surface.source.startswith("RAD RAD_RDR_2012")
    assert surface.usv_h == pytest.approx(surface.ugy_h * 3.05)
    assert 3 < surface.ugy_h < 30  # Mars surface: ~0.21 mGy/day = 8.75 uGy/h on average


def test_simulator_runs_every_astronaut_and_the_schedule(env):
    _, hub, _, _ = env
    for m in range(420, 520, 24):  # day 1 07:00-08:40: the 07:30 morning check falls in here
        hub.sim.tick(float(m))
    assert {d["astronautId"] for d in hub.devices() if d["bursts"] == 5} == {
        "astro-1",
        "astro-2",
        "astro-3",
        "astro-4",
    }
    sources = {
        r["source"] for r in hub.store.all("SELECT DISTINCT source FROM tests WHERE mission_minute > 0")
    }
    assert "onboard morning check" in sources


def test_urgent_alerts_go_now_and_the_rest_waits_for_the_day_end(env):
    client, hub, nasa, keys = env
    w = Wearable(client, keys["astro-1"])
    for hr in (70, 112, 112):
        w.send(hr=hr)
    hub.sync_tick()
    assert {r["type"] for r in nasa.saved.values()} == {"alert"}  # CHECK_VITALS went straight away
    hub.end_of_day(1)
    assert hub.store.scalar("SELECT COUNT(*) FROM outbox") == 0
    assert {"reading", "summary", "profile", "event"} <= {r["type"] for r in nasa.saved.values()}


def test_link_down_keeps_everything_and_drains_after(env):
    client, hub, nasa, keys = env
    w = Wearable(client, keys["astro-1"])
    client.post("/hub/link", json={"up": False})
    for _ in range(5):
        w.send()
    hub.end_of_day(1)
    assert nasa.saved == {} and hub.store.scalar("SELECT COUNT(*) FROM outbox") > 5
    client.post("/hub/link", json={"up": True})
    hub.sync_tick()  # the missed day-end batch goes as soon as the link is back
    assert hub.store.scalar("SELECT COUNT(*) FROM outbox") == 0
    row = next(r for r in client.get("/hub/verify").json()["rows"] if r["astronautId"] == "astro-1")
    assert row["ok"] and row["wearableSent"] == row["hubBursts"] == 5 and row["observations"] == 20


def test_sign_up_report_labs_and_agent(env):
    client, hub, nasa, _ = env
    r = client.post(
        "/hub/astronauts",
        json={
            "name": "Carl Simea",
            "age": 23,
            "sex": "m",
            "resting_hr": 64,
            "baseline": {"bp.sys": 118, "bogus.key": 3},
            "report": "Name: Carl",
        },
    ).json()
    assert r["id"] == "carl-simea"
    hub.sim.tick(600.0)
    body = client.get("/hub/body/carl-simea").json()
    assert body["values"]["bp.sys"] == 118 and "bogus.key" not in body["values"]
    assert hub.store.scalar("SELECT COUNT(*) FROM events WHERE astronaut_id='carl-simea'") > 50
    assert client.post("/hub/labs/carl-simea", json={"urine.calciumMgDay": 250, "x": 1}).json()["values"] == {
        "urine.calciumMgDay": 250.0
    }
    a = client.post("/hub/agent/carl-simea", json={"question": "How is my radiation?"}).json()
    assert "600 mSv" in a["answer"]
    assert client.post("/hub/report/text", content=b"not a pdf").status_code == 415


def test_demo_drawer(env):
    client, hub, _, _ = env
    assert client.post("/hub/demo/astro-2", json={"action": "fake"}).json()["blocked"]
    client.post("/hub/demo/astro-2", json={"action": "spacewalk"})
    hub.sim.tick(600.0)
    assert hub.store.recent_bursts("astro-2", 1)[0]["state"] == "spacewalk"
    client.post("/hub/demo/astro-2", json={"action": "wear", "on": False})
    hub.sim.tick(624.0)
    assert hub.store.burst_count("astro-2") == 1


def test_eva_dose_counts_only_the_current_spacewalk():
    rows = [
        {"state": s, "total_dose": t}
        for s, t in (
            ("awake", 1.0),
            ("spacewalk", 1.5),
            ("awake", 1.6),
            ("spacewalk", 1.7),
            ("spacewalk", 2.4),
        )
    ]
    dose, n = rules.eva_dose(rows)
    assert dose == pytest.approx(0.8) and n == 2


def test_ai_rewording_must_keep_the_numbers():
    from medvital.hub import ai

    assert ai.numbers_survive("HR 121 bpm, baseline 58", "Your heart is at 121 bpm; normal for you is 58.")
    assert not ai.numbers_survive("HR 121 bpm, baseline 58", "Your heart is at 120 bpm.")


def test_apps_are_served(env):
    client, *_ = env
    for path in ("/apps/", "/astronaut/", "/cloudflare/", "/body/", "/reports/astro-1_maya-okafor.pdf"):
        assert client.get(path).status_code == 200, path
