"""The astronaut's own buttons: sleep, leave the spacecraft (warning, then forced return), mood, skip ahead."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from medvital.hub import rules
from medvital.hub import settings as S
from medvital.hub.app import create_hub_app


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "EVA_WARN_AFTER_S", 0.05)
    monkeypatch.setattr(S, "EVA_RETURN_AFTER_WARN_S", 0.05)
    app = create_hub_app(data_dir=tmp_path, start_background=False)
    hub = app.state.hub
    hub.tick()
    yield TestClient(app), hub
    hub.store.close()


def test_sleep_button_counts_the_hours_and_logs_them(env):
    c, hub = env
    assert c.post("/hub/astronauts/astro-1/sleep", json={"asleep": True}).json()["asleep"] is True
    for _ in range(20):
        hub.tick()
    assert hub.sim.wearers["astro-1"].manual == "asleep"
    assert c.get("/hub/body/astro-1").json()["sleeping"] is not None
    out = c.post("/hub/astronauts/astro-1/sleep", json={"asleep": False}).json()
    assert out["asleep"] is False and out["hours"] >= 0
    assert hub.store.latest_tests("astro-1")["sleep.hours"]["source"] == "wearable sleep log (Sleep button)"


def test_spacewalk_warns_then_forces_the_return_and_logs_the_exposure(env):
    c, hub = env
    c.post("/hub/astronauts/astro-2/eva", json={"outside": True})
    assert c.post("/hub/astronauts/astro-2/sleep", json={"asleep": True}).status_code == 409  # not while outside
    time.sleep(0.06)
    hub.tick()
    eva = c.get("/hub/body/astro-2").json()["eva"]
    assert eva["warning"] and eva["warning"]["deadline"]
    assert hub.store.one("SELECT code FROM alerts WHERE astronaut_id='astro-2' ORDER BY time DESC")["code"] == rules.GO_INSIDE
    time.sleep(0.06)
    hub.tick()
    alert = c.get("/hub/body/astro-2").json()["alert"]
    assert alert["code"] == rules.RETURN_NOW and alert["reason"] == "eva_deadline"
    c.post(f"/hub/alerts/{alert['id']}/ack")
    body = c.get("/hub/body/astro-2").json()
    assert body["eva"] is None
    log = body["evaLog"][0]
    assert log["status"] == "done" and "called back inside" in log["detail"] and "mSv" in log["detail"]
    tests = hub.store.latest_tests("astro-2")
    assert tests["eva.doseMsv"]["origin"] == "modeled" and "eva.minutes" in tests


def test_going_back_inside_in_time_ends_the_spacewalk_without_alarm(env):
    c, hub = env
    c.post("/hub/astronauts/astro-3/eva", json={"outside": True})
    hub.tick()
    out = c.post("/hub/astronauts/astro-3/eva", json={"outside": False}).json()
    assert "minutes" in out and hub.eva_status("astro-3") is None
    assert not hub.store.one("SELECT 1 FROM alerts WHERE astronaut_id='astro-3' AND code='RETURN_NOW'")


def test_mood_and_sleep_both_off_asks_the_flight_surgeon_to_check_in(env):
    c, hub = env
    for h in (3.0, 3.2, 3.1):
        hub.add_measurements("astro-1", hub.clock.minute(), {"sleep.hours": h}, "simulated", "test")
    assert c.post("/hub/astronauts/astro-1/mood", json={"score": 2}).status_code == 200
    a = hub.store.one("SELECT * FROM alerts WHERE astronaut_id='astro-1' AND code=?", (rules.CHECK_IN,))
    assert a and "flight surgeon" in a["message"]
    assert c.post("/hub/astronauts/astro-1/mood", json={"score": 9}).status_code == 409


def test_sleep_mood_rule_needs_both():
    assert rules.sleep_mood([7.0, 7.1, 6.9], 7.0, 1) is None  # sleep as usual
    assert rules.sleep_mood([3.0, 3.0], 7.0, 4) is None  # mood fine
    assert rules.sleep_mood([10.0, 10.5, 9.8], 7.0, 2).code == rules.CHECK_IN  # too much sleep counts too


def test_urine_bone_panel_is_accepted_and_offered(env):
    c, hub = env
    panel = c.get("/hub/body/astro-1").json()["urinePanel"]
    assert {"urine.calciumMgDay", "urine.ntxNmolDay", "urine.dpdNmolDay"} <= {p["key"] for p in panel}
    assert c.post("/hub/labs/astro-1", json={"urine.ntxNmolDay": 420, "urine.calciumMgDay": 260}).status_code == 200
    assert hub.store.latest_tests("astro-1")["urine.ntxNmolDay"]["origin"] == "entered"


def test_skip_ahead_to_two_hours_before_the_next_solar_event(env):
    c, hub = env
    before = hub.clock.minute()
    out = c.post("/hub/skip", json={"to": "solar"}).json()
    assert "before the solar particle event" in out["what"] and hub.clock.minute() > before + 1000
    assert c.post("/hub/skip", json={"to": "day", "day": 1}).status_code == 409  # already passed
    c.post("/hub/astronauts/astro-1/eva", json={"outside": True})
    assert c.post("/hub/skip", json={"to": "solar"}).status_code == 409  # not while someone is outside


def test_local_check_without_cloudflare(env):
    _, hub = env
    hub.heartbeat()
    assert hub.checker["via"] == "local" and "Cloudflare not configured" in hub.checker["sentence"]["text"]
