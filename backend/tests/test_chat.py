"""The onboard agent as a chatbot: greetings, symptoms with common causes, danger signs, sending to NASA."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from medvital.hub import chat
from medvital.hub.app import create_hub_app


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("MEDVITAL_OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("MEDVITAL_CLOUDFLARE_URL", raising=False)
    app = create_hub_app(data_dir=tmp_path, start_background=False)
    hub = app.state.hub
    for _ in range(3):
        hub.tick()
    yield TestClient(app), hub
    hub.store.close()


def ask(c, q, history=None):
    return c.post("/hub/agent/astro-1", json={"question": q, "history": history or []}).json()


def test_greeting_is_a_greeting(env):
    c, _ = env
    r = ask(c, "hello")
    assert r["answer"].startswith("Hello Maya") and r["source"] == "onboard agent · built-in"


def test_symptom_gives_common_causes_numbers_and_no_diagnosis(env):
    c, _ = env
    r = ask(c, "my head hurts")
    assert r["symptoms"] == ["headache"]
    assert "carbon dioxide" in r["answer"] and "Source:" in r["answer"] and "not a diagnosis" in r["answer"]
    assert "heart rate" in r["answer"] and "bpm" in r["answer"]


def test_danger_sign_raises_an_urgent_alert(env):
    c, hub = env
    r = ask(c, "I have chest pain")
    assert r["danger"] == "chest pain" and "flight surgeon now" in r["answer"]
    a = hub.store.one("SELECT * FROM alerts WHERE reason='danger_sign'")
    assert a["code"] == "CHECK_VITALS"
    assert hub.store.scalar("SELECT COUNT(*) FROM outbox WHERE urgent=1") >= 1


def test_send_to_flight_surgeon_queues_the_chat_for_nasa(env):
    c, hub = env
    h = [{"role": "user", "content": "my head hurts"}, {"role": "assistant", "content": "Headache in space ..."}]
    r = c.post("/hub/agent/astro-1/send", json={"transcript": h}).json()
    assert r["sent"] and r["symptoms"] == ["headache"]
    row = hub.store.one("SELECT * FROM records WHERE type='consult'")
    assert row and row["astronaut_id"] == "astro-1"
    assert c.post("/hub/agent/astro-1/send", json={"transcript": []}).status_code == 409


def test_model_numbers_must_match_the_data():
    assert chat.numbers_ok("Your heart rate is 64 bpm.", '{"heartRate": 64}')
    assert not chat.numbers_ok("Your heart rate is 90 bpm.", '{"heartRate": 64}')


def test_symptom_and_danger_detection():
    assert chat.find_symptoms("I feel nauseous and my back hurts") == ["nausea", "back pain"]
    assert chat.find_danger("I can't breathe") == "trouble breathing"
    assert chat.find_danger("my head hurts") is None
