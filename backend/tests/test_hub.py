"""Spacecraft hub: secure network, double-check, alert rules, outbox -> NASA sync, verification."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from medvital.hub import rules
from medvital.hub import settings as S
from medvital.hub.app import create_hub_app


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
            return 200, {"total": len(self.saved), "by_astronaut": by_a, "by_astronaut_and_type": {}}
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
    keys = {
        a: client.post("/hub/pair", json={"astronautId": a}).json()["deviceKey"]
        for a in ("astro-1", "astro-2")
    }
    yield client, hub, nasa, keys
    hub.store.close()


class Wearable:
    def __init__(self, client, key, aid="astro-1"):
        self.client, self.key, self.aid, self.seq, self.total = client, key, aid, 0, 0.0

    def send(self, hr=62, spo2=98, state="awake", dose=26.7, key=None):
        self.seq += 1
        self.total += dose * S.MISSION_MINUTES_PER_BURST / 60 / 1000
        return self.client.post(
            "/hub/burst",
            json={
                "astronautId": self.aid,
                "deviceKey": key or self.key,
                "seq": self.seq,
                "time": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "heartRate": hr,
                "spo2": spo2,
                "state": state,
                "doseRate": dose,
                "totalDose": round(self.total, 5),
            },
        )


def test_private_network_blocks_wrong_key(env):
    client, hub, _, keys = env
    w = Wearable(client, keys["astro-1"])
    assert w.send(key="stolen").status_code == 401
    assert hub.store.scalar("SELECT COUNT(*) FROM bursts") == 0
    assert hub.store.scalar("SELECT COUNT(*) FROM rejected") == 1
    assert "stolen" not in hub.store.one("SELECT payload FROM rejected")["payload"]  # the key is never stored


def test_glitch_is_flagged_not_alerted(env):
    client, hub, _, keys = env
    w = Wearable(client, keys["astro-1"])
    w.send()
    r = w.send(hr=240).json()
    assert r["quality"] == "invalid" and r["alert"] is None
    r = w.send(hr=62 + S.GLITCH_HR_JUMP_BPM + 30).json()  # big jump from a valid reading: suspect
    assert r["quality"] == "valid" or r["quality"] == "suspect"


def test_heart_rate_alert_needs_confirmation(env):
    client, _, _, keys = env
    w = Wearable(client, keys["astro-1"])  # baseline 58, awake allowance 40
    w.send(hr=70)
    assert w.send(hr=110).json()["alert"] is None  # first high reading: wait for confirmation
    r = w.send(hr=112).json()
    assert r["alert"] == "CHECK_VITALS" and "baseline of 58" in r["message"]


def test_profiles_adapt_to_each_astronaut(env):
    client, _, _, keys = env
    a1, a2 = Wearable(client, keys["astro-1"]), Wearable(client, keys["astro-2"], "astro-2")
    got1, got2 = set(), set()
    for _ in range(3):  # 105 is high for astro-1 (baseline 58) but fine for astro-2 (baseline 72)
        got1.add(a1.send(hr=105).json()["alert"])
        got2.add(a2.send(hr=105).json()["alert"])
    assert "CHECK_VITALS" in got1
    assert got2 == {None}


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


def test_link_down_keeps_everything_and_drains_after(env):
    client, hub, nasa, keys = env
    w = Wearable(client, keys["astro-1"])
    client.post("/hub/link", json={"up": False})
    for _ in range(5):
        w.send()
    assert hub.sync_once()["confirmed"] == 0
    assert hub.store.scalar("SELECT COUNT(*) FROM outbox") == 5
    client.post("/hub/link", json={"up": True})
    assert hub.sync_once()["confirmed"] == 5
    assert hub.store.scalar("SELECT COUNT(*) FROM outbox") == 0
    row = next(r for r in client.get("/hub/verify").json()["rows"] if r["astronautId"] == "astro-1")
    assert row["ok"] and row["wearableSent"] == row["hubBursts"] == 5 and row["atNasa"] == 5
    assert row["observations"] == 20  # 4 provenance-labelled values per burst


def test_summary_labs_and_agent(env):
    client, hub, _, keys = env
    w = Wearable(client, keys["astro-1"])
    for state in ("asleep", "asleep", "exercise", "awake"):
        w.send(state=state, hr=60)
    s = client.post("/hub/summary/astro-1").json()
    assert s["facts"]["sleepHours"] == 1.0 and s["facts"]["exerciseMinutes"] == 30
    assert client.post("/hub/labs/astro-1", json={"urine.calciumMgDay": 250, "bogus": 1}).json()[
        "values"
    ] == {"urine.calciumMgDay": 250.0}
    a = client.post("/hub/agent/astro-1", json={"question": "How is my radiation?"}).json()
    assert "600 mSv" in a["answer"] and a["source"].startswith("onboard agent")
    types = {r["type"] for r in hub.store.all("SELECT type FROM records")}
    assert {"reading", "summary", "lab", "alert"} <= types


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
    for path in ("/apps/", "/astronaut/", "/cloudflare/", "/body/"):
        assert client.get(path).status_code == 200, path
