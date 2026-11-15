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


def test_flight_surgeon_views(nasa):
    client, _ = nasa
    mission = {"minute": 2000.0, "day": 2, "time": "09:20", "phase": "cruise", "phaseLabel": "Cruise to Mars"}
    prof = {"name": "Maya Okafor", "role": "Commander", "resting_hr": 58, "spo2": 98, "prior_career_msv": 112,
            "baseline": {"bp.sys": 112}, "report": "astro-1_maya-okafor"}
    recs = [
        {**fmt.make_record("p", fmt.TYPE_PROFILE, "astro-1", "2026-11-14T12:00:00Z", {"profile": prof, "report": "Name: Maya"}), "mission": mission},
        {**reading("r1"), "mission": mission},
        {**fmt.make_record("t1", fmt.TYPE_TEST, "astro-1", "2026-11-14T12:01:00Z",
                           {"values": {"bp.sys": 118}, "origin": "simulated", "source": "onboard morning check"}), "mission": mission},
        {**fmt.make_record("e1", fmt.TYPE_EVENT, "crew", "2026-11-14T12:01:00Z",
                           {"m_start": 3000, "m_end": 3000, "kind": "space_weather", "title": "Class X1.6 solar flare",
                            "source": "NASA DONKI 2024-05-03T02:11:00-FLR-001"}), "mission": mission},
        {**fmt.make_record("e0", fmt.TYPE_EVENT, "crew", "2026-11-14T12:01:00Z",
                           {"m_start": 100, "m_end": 200, "kind": "test", "title": "already over"}), "mission": mission},
    ]
    client.post("/batch", json={"records": recs})
    m = client.get("/api/mission").get_json()
    assert m["now"]["day"] == 2 and m["crew"][0]["name"] == "Maya Okafor"
    assert [e["title"] for e in m["upcoming"]] == ["Class X1.6 solar flare"]  # past events are not upcoming
    a = client.get("/api/astronaut/astro-1").get_json()
    bp = next(r for r in a["compare"] if r["label"] == "Blood pressure, systolic")
    assert bp["preflight"] == 112 and bp["now"] == 118 and bp["change"] == 6
    assert a["reportPdf"] == "/reports/astro-1_maya-okafor.pdf" and a["report"] == "Name: Maya"
    assert client.get("/reports/astro-1_maya-okafor.pdf").status_code == 200
    assert client.get("/api/astronaut/nobody").status_code == 404


def test_osdr_studies_behind_each_risk(nasa):
    client, _ = nasa
    d = client.get("/api/osdr").get_json()
    if d["topics"]:  # data/nasa/osdr_studies.json present
        heart = next(t for t in d["topics"] if t["key"] == "heart")
        assert heart["studies"] and heart["studies"][0]["accession"].startswith("OSD-")


def test_pulls_from_the_cloudflare_worker_with_a_cursor(nasa, monkeypatch):
    """Cloudflare mode: records come from the Worker's D1; the cursor moves only after they are saved."""
    _, app_module = nasa
    d1 = [reading(f"cf{i}", "astro-2" if i % 2 else "astro-1") for i in range(1, 8)]
    asked = []

    def fake_worker(method, path, body=None, timeout=10):
        after = int(path.split("after=")[1].split("&")[0])
        asked.append(after)
        page = [{"seq": i + 1, "record": r} for i, r in enumerate(d1) if i + 1 > after][:5]
        return 200, {"records": page, "next": page[-1]["seq"] if page else after, "more": len(page) == 5}

    monkeypatch.setattr(app_module, "worker", fake_worker)
    assert app_module.pull_once() == 7
    assert asked == [0, 5]
    assert app_module.meta("cloudflare_cursor") == "7"
    assert app_module.pull_once() == 0 and asked[-1] == 7  # nothing new, nothing pulled twice

    d1.append(reading("cf1"))  # a retry stored in D1 again: NASA still has it once
    assert app_module.pull_once() == 1
    client, _ = nasa
    assert client.get("/stats").get_json()["total"] == 7


def test_unreachable_worker_does_not_move_the_cursor(nasa, monkeypatch):
    _, app_module = nasa
    monkeypatch.setattr(app_module, "worker", lambda *a, **k: (401, {"error": "wrong key"}))
    assert app_module.pull_once() == 0
    assert app_module.meta("cloudflare_cursor") is None
    assert app_module.pull_state["lastError"] == "Worker refused the key (401)"


def test_cut_link_to_nasa_retries_and_logs_then_catches_up(nasa, monkeypatch):
    """Cloudflare answers 503 while the link to NASA is cut: NASA logs each retry, then receives what waited."""
    _, app_module = nasa
    app_module.pull_state.update(linkDown=False, retries=0)
    d1 = [reading(f"w{i}") for i in range(1, 4)]
    down = {"v": True}

    def fake_worker(method, path, body=None, timeout=10):
        if down["v"]:
            return 503, {"error": "link to NASA down", "waiting": len(d1)}
        after = int(path.split("after=")[1].split("&")[0])
        page = [{"seq": i + 1, "record": r} for i, r in enumerate(d1) if i + 1 > after]
        return 200, {"records": page, "next": page[-1]["seq"] if page else after, "more": False}

    monkeypatch.setattr(app_module, "worker", fake_worker)
    app_module.pull_once()
    app_module.pull_once()
    assert app_module.pull_state["linkDown"] and app_module.pull_state["retries"] == 1
    assert app_module.pull_state["waiting"] == 3
    down["v"] = False
    assert app_module.pull_once() == 3
    events = [r["event"] for r in app_module.link_log_rows()]
    assert events[:3] == ["restored", "retry", "down"]


def test_day_report(nasa):
    client, _ = nasa
    r = reading("d1")
    r["data"]["missionMinute"] = 1500.0  # mission day 2
    client.post("/batch", json={"records": [r]})
    assert client.get("/api/astronaut/astro-1/days").get_json() == [2]
    day = client.get("/api/astronaut/astro-1/day/2").get_json()
    assert day["readings"] == 1 and day["heartRate"]["avg"] == 62
