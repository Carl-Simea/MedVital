"""NASA receiver tests (replace the old manual test_step1_batches.py / test_step2_link.py / fake_data.py).

Run from the repo root:   .venv/bin/python -m pytest nasa        (Windows: .venv\\Scripts\\python -m pytest nasa)
No server needs to be running: Flask's test client talks to the app directly.
"""

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import record_format as fmt  # noqa: E402


@pytest.fixture
def nasa(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDVITAL_NASA_DB", str(tmp_path / "mission.db"))
    import app as app_module

    app_module = importlib.reload(app_module)  # picks up the temporary database
    app_module.link["up"] = True
    return app_module.app.test_client(), app_module


def reading(rid, astronaut="astro-1", hr=62, quality="valid"):
    return fmt.make_record(rid, fmt.TYPE_READING, astronaut, "2026-11-14T12:00:00.000Z",
                           {"heartRate": hr, "spo2": 98, "state": "awake", "doseRate": 26.7, "totalDose": 0.1,
                            "quality": quality})


def test_batches_are_idempotent(nasa):
    client, _ = nasa
    batch = [reading("r1"), reading("r2"), reading("r3", "astro-2")]
    assert client.post("/batch", json={"records": batch}).get_json() == {"saved": ["r1", "r2", "r3"]}
    # the same id again (a retry after a lost answer): confirmed again, saved once
    again = client.post("/batch", json={"records": [batch[0], reading("r4")]}).get_json()
    assert again == {"saved": ["r1", "r4"]}
    stats = client.get("/stats").get_json()
    assert stats["total"] == 4 and stats["by_astronaut"] == {"astro-1": 3, "astro-2": 1}


def test_records_without_id_are_not_confirmed(nasa):
    client, _ = nasa
    out = client.post("/batch", json={"records": [{"type": "reading"}, reading("ok")]}).get_json()
    assert out == {"saved": ["ok"]}
    assert client.post("/batch", json={"oops": []}).status_code == 400


def test_link_down_refuses_and_saves_nothing(nasa):
    client, _ = nasa
    assert client.post("/link", json={"up": False}).get_json() == {"up": False}
    assert client.post("/batch", json={"records": [reading("x1")]}).status_code == 503
    assert client.get("/stats").get_json()["total"] == 0
    client.post("/link", json={"up": True})
    assert client.post("/batch", json={"records": [reading("x1")]}).get_json() == {"saved": ["x1"]}


def test_mission_record_screen_data(nasa):
    client, _ = nasa
    records = [
        reading("a"), reading("b", hr=240, quality="invalid"),
        fmt.make_record("c", fmt.TYPE_ALERT, "astro-1", "2026-11-14T12:01:00Z", {"code": "RETURN_NOW", "message": "Head back in."}),
        fmt.make_record("d", fmt.TYPE_SUMMARY, "astro-1", "2026-11-14T12:02:00Z", {"text": "Slept 7 h."}),
        fmt.make_record("e", fmt.TYPE_LAB, "astro-1", "2026-11-14T12:03:00Z", {"values": {"urine.calciumMgDay": 250}}),
    ]
    client.post("/batch", json={"records": records})
    a = client.get("/records").get_json()["astronauts"][0]
    assert len(a["readings"]) == 1 and a["flagged"] == 1  # the glitched reading is saved but not charted
    assert a["alerts"][0]["code"] == "RETURN_NOW"
    assert a["summaries"][0]["text"] == "Slept 7 h."
    assert a["labs"][0]["text"] == "Urinary calcium 250 mg/day"
    assert "deviceKey" not in str(a)


def test_screen_and_chart_library_are_served(nasa):
    client, _ = nasa
    assert client.get("/").status_code == 200
    assert client.get("/vendor/chart.umd.js").status_code == 200
