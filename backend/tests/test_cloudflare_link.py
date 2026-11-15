"""The hub talking to Earth through the Cloudflare Worker (cloudflare/src/index.js).

A small HTTP server here follows the Worker's contract (key header, /outbox, /link, /stats, /ai), so the
real urllib path in Hub._nasa and ai.workers_ai is exercised. The Worker itself is tested with wrangler.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from medvital.hub import ai
from medvital.hub import settings as S
from medvital.hub.app import create_hub_app

KEY = "test-key-not-a-secret"


class FakeWorker(BaseHTTPRequestHandler):
    records: dict[str, dict] = {}
    up = True
    calls: list[tuple[str, str]] = []
    heartbeats: list[dict] = []

    def log_message(self, *_):  # keep pytest output clean
        pass

    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle(self):
        cls = type(self)
        cls.calls.append((self.command, self.path))
        if self.headers.get("x-medvital-key") != KEY:
            return self._send(401, {"error": "missing or wrong x-medvital-key"})
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n) or b"null") if n else None
        route = f"{self.command} {self.path.split('?')[0]}"
        if route == "POST /outbox":  # the spacecraft always reaches Cloudflare; the switch is Cloudflare -> NASA
            for r in body["records"]:
                cls.records[str(r["id"])] = r
            return self._send(200, {"saved": [str(r["id"]) for r in body["records"]]})
        if route == "GET /link":
            return self._send(200, {"up": cls.up})
        if route == "POST /link":
            cls.up = bool(body["up"])
            return self._send(200, {"up": cls.up})
        if route == "GET /stats":
            by_a: dict[str, int] = {}
            for r in cls.records.values():
                by_a[r["astronautId"]] = by_a.get(r["astronautId"], 0) + 1
            return self._send(200, {"total": len(cls.records), "by_astronaut": by_a})
        if route == "POST /heartbeat":
            cls.heartbeats.append(body)
            rep = body["report"]
            return self._send(200, {"at": "now", "parts": {"hub": {"up": True}, "devices": rep["devices"]},
                                    "link": {"up": cls.up, "retryEveryS": 3},
                                    "db": {"spacecraftConfirmed": rep["confirmed"], "cloudflare": len(cls.records),
                                           "nasa": 0, "waitingAtCloudflare": len(cls.records), "ok": True},
                                    "log": [], "sentence": {"text": "ok", "source": "rules"}})
        if route == "GET /donki":
            return self._send(200, {"events": [{"id": "2026-11-10T01:00:00-FLR-001", "type": "FLR",
                                                "start": "2026-11-10T01:00Z", "end": "2026-11-10T01:30Z",
                                                "summary": "Class X1.0 solar flare", "link": None}]})
        if route == "POST /ai":
            return self._send(200, {"text": f"Plain words. {body['prompt'].split(':', 1)[-1].strip()}"})
        return self._send(404, {"error": "not found"})

    do_GET = do_POST = _handle


@pytest.fixture
def worker():
    FakeWorker.records, FakeWorker.up, FakeWorker.calls, FakeWorker.heartbeats = {}, True, [], []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeWorker)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def hub_via_worker(tmp_path, worker, monkeypatch):
    monkeypatch.setattr(S, "CLOUDFLARE_URL", worker)
    monkeypatch.setattr(S, "CLOUDFLARE_KEY", KEY)
    app = create_hub_app(data_dir=tmp_path, nasa_url="http://nasa.invalid", start_background=False)
    hub = app.state.hub
    yield hub
    hub.store.close()


def test_outbox_goes_to_the_worker_with_the_key_and_nothing_is_lost(hub_via_worker):
    hub = hub_via_worker
    assert hub.via == "cloudflare" and hub.link()["up"] is True
    created = hub.store.scalar("SELECT COUNT(*) FROM outbox")
    hub.end_of_day(1)
    assert hub.store.scalar("SELECT COUNT(*) FROM outbox") == 0
    assert len(FakeWorker.records) >= created > 0
    assert ("POST", "/outbox") in FakeWorker.calls and ("POST", "/batch") not in FakeWorker.calls
    assert all(r["ok"] for r in hub.verify()["rows"])  # "NASA has" now reads the Worker's D1 counts


def test_cutting_the_link_to_nasa_still_lets_the_spacecraft_reach_cloudflare(hub_via_worker):
    """The switch sits between Cloudflare and NASA: the spacecraft keeps delivering, D1 keeps everything."""
    hub = hub_via_worker
    hub.link(False)
    assert FakeWorker.up is False and hub.link()["up"] is False
    hub.end_of_day(1)
    assert hub.store.scalar("SELECT COUNT(*) FROM outbox") == 0 and FakeWorker.records
    assert hub.sync_state["dayReport"]["delivered"] is True
    hub.link(True)
    assert FakeWorker.up is True


def test_heartbeat_reports_to_the_cloudflare_checker(hub_via_worker):
    hub = hub_via_worker
    hub.tick()
    hub.heartbeat()
    rep = FakeWorker.heartbeats[-1]
    assert rep["node"] == "hub" and {d["id"] for d in rep["report"]["devices"]} >= {"astro-1", "astro-4"}
    assert hub.checker["via"] == "cloudflare" and hub.checker["db"]["ok"] is True


def test_space_weather_comes_through_cloudflare(hub_via_worker):
    hub = hub_via_worker
    hub.refresh_space_weather()
    live = hub.live_space_weather()
    assert live and live[0]["source"] == "NASA DONKI (live, through Cloudflare)" and "ended" in live[0]["summary"]


def test_wrong_key_is_refused_and_records_stay(tmp_path, worker, monkeypatch):
    monkeypatch.setattr(S, "CLOUDFLARE_URL", worker)
    monkeypatch.setattr(S, "CLOUDFLARE_KEY", "wrong")
    hub = create_hub_app(data_dir=tmp_path, start_background=False).state.hub
    try:
        before = hub.store.scalar("SELECT COUNT(*) FROM outbox")
        hub.sync_once()
        assert FakeWorker.records == {} and hub.store.scalar("SELECT COUNT(*) FROM outbox") == before
        assert hub.sync_state["lastError"] == "Cloudflare refused the key (401)"
    finally:
        hub.store.close()


def test_workers_ai_runs_through_the_worker(worker, monkeypatch):
    monkeypatch.setenv("MEDVITAL_CLOUDFLARE_URL", worker)
    monkeypatch.setenv("MEDVITAL_CLOUDFLARE_KEY", KEY)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    text, source, _ = ai.reword("Dose today 0.21 mGy.", "summary")
    assert source == "Workers AI" and "0.21" in text
    assert ("POST", "/ai") in FakeWorker.calls
