"""HTTP routes of the spacecraft hub (``/hub/*``). Record format: nasa/record_format.py."""

from __future__ import annotations

import io
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from medvital.hub import ai
from medvital.hub import mission as M
from medvital.hub import settings as S
from medvital.hub.actions import ActionError
from medvital.hub.service import Hub
from medvital.hub.store import TABLES

router = APIRouter(prefix="/hub", tags=["hub"])
JsonBody = Annotated[dict, Body()]

# Everything an astronaut may type in (the 3D body dashboard's indicator keys).
ENTRY_KEYS = {
    "hr.rest",
    "bp.sys",
    "bp.dia",
    "spo2.pct",
    "resp.rate",
    "temp.c",
    "glucose.mgdl",
    "hemoglobin.gdl",
    "vitd.ngml",
    "urine.volumeL",
    "urine.calciumMgDay",
    "pvt.meanRtMs",
    "pvt.lapses",
    "sleep.hours",
    "sleep.quality",
    "back.pain",
    "mass.changePct",
    "strength.changePct",
    "aerobic.changePct",
    *S.URINE_BONE_PANEL,
    "mood.score",
    "exercise.minPerWeek",
    "exercise.resistiveDays",
    "nutrition.energyPct",
    "nutrition.proteinGkg",
    "nutrition.fluidL",
    "sans.hyperopicShiftD",
}


def _hub(request: Request) -> Hub:
    return request.app.state.hub


def _astronaut(hub: Hub, aid: str) -> dict[str, Any]:
    a = hub.store.astronaut(aid)
    if a is None:
        raise HTTPException(404, f"unknown astronaut {aid!r}")
    return a


@router.get("/config")
def config() -> dict[str, Any]:
    return S.public_config()


@router.get("/clock")
def clock(request: Request) -> dict[str, Any]:
    return _hub(request).clock_view()


@router.get("/status")
def status(request: Request) -> dict[str, Any]:
    hub = _hub(request)
    return {
        "sync": hub.sync_state,
        "outbox": hub.store.scalar("SELECT COUNT(*) FROM outbox"),
        "outboxUrgent": hub.store.scalar("SELECT COUNT(*) FROM outbox WHERE urgent=1"),
        "tables": hub.store.counts(),
        "donki": hub.donki_state,
        "nasaUrl": hub.nasa_url,
        "via": hub.via,
        "cloudflareUrl": hub.cf_url,
        "checker": hub.checker,
        "dayReport": hub.sync_state.get("dayReport"),
        "evas": {aid: hub.eva_status(aid) for aid in list(hub.evas)},
        "solarEvent": hub.solar_active(),
        "clock": hub.clock_view(),
        "rad": M.rad_summary(),
        "ai": {
            "workersAi": ai.workers_ai_enabled(),
            "workersAiModel": ai.WORKERS_AI_MODEL,
            "onboardAgent": ai.agent_model() or "rules",
        },
    }


@router.get("/devices")
def devices(request: Request) -> list[dict[str, Any]]:
    return _hub(request).devices()


@router.get("/events")
def events(
    request: Request,
    astronaut: str | None = None,
    upcoming: bool = True,
    limit: int = 40,
    kind: str | None = None,
) -> list[dict[str, Any]]:
    kinds = tuple(kind.split(",")) if kind else None
    return _hub(request).events(astronaut, upcoming=upcoming, limit=max(1, min(limit, 500)), kinds=kinds)


# ------------------------------------------------------------------------------- crew and sign-up
@router.get("/astronauts")
def astronauts(request: Request) -> list[dict[str, Any]]:
    return [
        {
            "id": a["id"],
            "name": a["name"],
            "role": a["role"],
            "profile": a["profile"],
            "hasReport": bool(a["report"]),
        }
        for a in _hub(request).store.astronauts()
    ]


@router.post("/astronauts")
def sign_up(request: Request, body: JsonBody) -> dict[str, Any]:
    """New astronaut: name and basic pre-flight values (typed and/or read from a report)."""

    def num(key: str, lo: float, hi: float, default: float | None = None) -> float | None:
        v = body.get(key, default)
        if v in (None, ""):
            return default
        try:
            v = float(v)
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, f"{key} must be a number") from exc
        if not lo <= v <= hi:
            raise HTTPException(422, f"{key} must be between {lo:g} and {hi:g}")
        return v

    name = str(body.get("name") or "").strip()[:60]
    if not name:
        raise HTTPException(422, "name is required")
    baseline = {
        k: float(v)
        for k, v in (body.get("baseline") or {}).items()
        if k in ENTRY_KEYS and isinstance(v, (int, float))
    }
    profile = {
        "name": name,
        "role": str(body.get("role") or "Crew member")[:40],
        "age": int(num("age", 18, 80, 40)),
        "sex": "m" if str(body.get("sex", "f")).lower().startswith("m") else "f",
        "height_cm": num("height_cm", 120, 220, 170),
        "weight_kg": num("weight_kg", 35, 160, 70),
        "resting_hr": num("resting_hr", 30, 120, baseline.get("hr.rest", 65)),
        "spo2": num("spo2", 85, 100, baseline.get("spo2.pct", 97)),
        "sleep_target_h": num("sleep_target_h", 4, 10, baseline.get("sleep.hours", 7.0)),
        "prior_career_msv": num("prior_career_msv", 0, 600, 0),
        "exercise_hour": num("exercise_hour", 0, 23, 16.0),
        "baseline": baseline,
        "report": None,
        "note": "Signed up in MedVital. Pre-flight values as entered; everything else is simulated from them.",
    }
    a = _hub(request).add_astronaut(profile, (str(body.get("report") or "")[:20000] or None))
    return {"id": a["id"], "name": a["name"]}


@router.get("/astronauts/{aid}")
def astronaut(aid: str, request: Request) -> dict[str, Any]:
    hub = _hub(request)
    _astronaut(hub, aid)
    return hub.astronaut_view(aid)


@router.get("/astronauts/{aid}/report", response_class=PlainTextResponse)
def report(aid: str, request: Request) -> str:
    a = _astronaut(_hub(request), aid)
    if not a["report"]:
        raise HTTPException(404, "no report on file")
    return a["report"]


@router.post("/report/text")
async def report_text(request: Request) -> dict[str, Any]:
    """Text of an uploaded PDF report (the browser reads .txt/.csv/.json itself)."""
    raw = await request.body()
    if not raw.startswith(b"%PDF"):
        raise HTTPException(415, "send a PDF; text files are read in the browser")
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise HTTPException(501, "PDF reading needs pypdf (pip install pypdf)") from exc
    try:
        text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(raw[:5_000_000])).pages[:20])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"could not read this PDF: {exc}") from exc
    return {"text": text}


@router.post("/pair")
def pair(request: Request, body: JsonBody) -> dict[str, Any]:
    """Docking a real wearable at its charging station hands it its secret key (simulated pairing)."""
    hub = _hub(request)
    a = _astronaut(hub, str(body.get("astronautId")))
    hub.net.add("pair", [a["id"], "tunnel", "worker"], "ok", f"{a['id']} wearable paired at its dock")
    return {"astronautId": a["id"], "deviceKey": a["device_key"], "name": a["name"], "profile": a["profile"]}


@router.post("/burst")
def burst(request: Request, body: JsonBody) -> JSONResponse:
    code, answer = _hub(request).handle_burst(body)
    return JSONResponse(answer, status_code=code)


@router.get("/crew")
def crew(request: Request) -> list[dict[str, Any]]:
    return _hub(request).crew()


@router.get("/body/{aid}")
def body_measurements(aid: str, request: Request) -> dict[str, Any]:
    """Everything the astronaut's 3D body view shows, every second."""
    hub = _hub(request)
    a = _astronaut(hub, aid)
    meas = hub.measurements(aid)
    # an active RETURN_NOW always wins: a later note (e.g. "summary ready") must not hide it
    alert = hub.store.one(
        "SELECT * FROM alerts WHERE astronaut_id=? AND code='RETURN_NOW' AND status='active' ORDER BY time DESC LIMIT 1",
        (aid,),
    ) or hub.store.one("SELECT * FROM alerts WHERE astronaut_id=? ORDER BY time DESC LIMIT 1", (aid,))
    return {
        "id": aid,
        "name": a["name"],
        "role": a["role"],
        "clock": hub.clock_view(),
        **meas,
        "alert": alert,
        "upcoming": hub.events(aid, limit=8),
        "spaceWeather": hub.events(None, kinds=("space_weather",), limit=5),
        "lastSummary": hub.store.one(
            "SELECT * FROM summaries WHERE astronaut_id=? ORDER BY time DESC LIMIT 1", (aid,)
        ),
        "device": next((d for d in hub.devices() if d["astronautId"] == aid), None),
        "eva": hub.eva_status(aid),
        "sleeping": hub.sleeping_hours(aid),
        "evaLog": hub.events(aid, upcoming=False, kinds=("eva",), limit=6),
        "liveSpaceWeather": hub.live_space_weather(6),
        "urinePanel": [{"key": k, "label": lab, "unit": u} for k, (lab, u) in S.URINE_BONE_PANEL.items()],
    }


def _act(fn, *args):
    try:
        return fn(*args)
    except ActionError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/astronauts/{aid}/sleep")
def sleep(aid: str, request: Request, body: JsonBody) -> dict[str, Any]:
    """The astronaut's Sleep / Wake up button."""
    hub = _hub(request)
    _astronaut(hub, aid)
    return _act(hub.set_sleep, aid, bool(body.get("asleep", True)))


@router.post("/astronauts/{aid}/eva")
def eva(aid: str, request: Request, body: JsonBody) -> dict[str, Any]:
    """Leave the spacecraft ({"outside": true}) or go back inside ({"outside": false})."""
    hub = _hub(request)
    _astronaut(hub, aid)
    if body.get("outside", True):
        return _act(hub.start_eva, aid)
    with hub._lock:
        for a in hub.store.all(
            "SELECT id FROM alerts WHERE astronaut_id=? AND code='RETURN_NOW' AND status='active'", (aid,)
        ):
            hub.store.run("UPDATE alerts SET status='acknowledged' WHERE id=?", (a["id"],))
        return hub.end_eva(aid) or {"outside": False}


@router.post("/astronauts/{aid}/mood")
def mood(aid: str, request: Request, body: JsonBody) -> dict[str, Any]:
    hub = _hub(request)
    _astronaut(hub, aid)
    try:
        score = int(body.get("score"))
    except (TypeError, ValueError) as e:
        raise HTTPException(422, "score is 1 to 5") from e
    return _act(hub.add_mood, aid, score)


@router.post("/skip")
def skip(request: Request, body: JsonBody) -> dict[str, Any]:
    """Demo drawer: jump the mission clock ahead (to 2 h before the next solar event, or to a day)."""
    hub = _hub(request)
    day = body.get("day")
    return _act(hub.skip_ahead, str(body.get("to") or "solar"), int(day) if day else None)


@router.get("/checker")
def checker(request: Request) -> dict[str, Any]:
    return _hub(request).checker


@router.post("/demo/{aid}")
def demo(aid: str, request: Request, body: JsonBody) -> dict[str, Any]:
    """The astronaut view's hidden Demo drawer."""
    hub = _hub(request)
    _astronaut(hub, aid)
    hub.sim.sync_crew()
    w = hub.sim.wearers[aid]
    action = str(body.get("action") or "")
    m = hub.clock.minute()
    if action in S.SCENARIOS:
        hub.sim.set_scenario(aid, action, m)
    elif action == "glitch":
        w.glitch_next = True
    elif action == "wear":
        w.worn = bool(body.get("on", True))
        hub.net.add(
            "pair",
            [aid, "tunnel"],
            "ok" if w.worn else "failed",
            f"{aid} wearable {'put on' if w.worn else 'taken off'}",
            astronaut=aid,
        )
    elif action == "fake":
        code, _ = hub.handle_burst(
            {
                "astronautId": aid,
                "deviceKey": "stolen-key",
                "time": "x",
                "heartRate": 70,
                "spo2": 98,
                "state": "awake",
                "doseRate": 1,
                "totalDose": 0,
            }
        )
        return {"ok": True, "blocked": code == 401}
    elif action == "solar":
        return {"ok": True, **hub.replay_solar_event()}
    elif action == "summary":
        return {"ok": True, "summary": hub.daily_summary(aid)}
    else:
        raise HTTPException(422, "unknown action")
    return {"ok": True, "scenario": w.scenario, "worn": w.worn}


@router.post("/alerts/{alert_id}/ack")
def ack(alert_id: str, request: Request) -> dict[str, Any]:
    if not _hub(request).acknowledge(alert_id):
        raise HTTPException(404, "unknown alert")
    return {"ok": True}


@router.post("/labs/{aid}")
def labs(aid: str, request: Request, body: JsonBody) -> dict[str, Any]:
    hub = _hub(request)
    _astronaut(hub, aid)
    values = {k: float(v) for k, v in body.items() if k in ENTRY_KEYS and isinstance(v, (int, float))}
    if not values:
        raise HTTPException(422, "send at least one known measurement")
    return hub.add_labs(aid, values)


@router.post("/agent/{aid}")
def agent(aid: str, request: Request, body: JsonBody) -> dict[str, Any]:
    hub = _hub(request)
    _astronaut(hub, aid)
    q = str(body.get("question") or "").strip()
    if not q:
        raise HTTPException(422, "question is empty")
    return hub.ask(aid, q[:500])


@router.post("/summary/{aid}")
def summary(aid: str, request: Request) -> dict[str, Any]:
    hub = _hub(request)
    _astronaut(hub, aid)
    out = hub.daily_summary(aid)
    if out is None:
        raise HTTPException(409, "no readings yet")
    return out


@router.get("/space-weather")
def space_weather(request: Request) -> dict[str, Any]:
    """Live DONKI events (through Cloudflare when configured) and the replayed mission calendar."""
    hub = _hub(request)
    return {"live": hub.live_space_weather(12), "state": hub.donki_state,
            "calendar": hub.events(None, kinds=("space_weather",), limit=12)}


@router.post("/space-weather/replay")
def replay(request: Request) -> dict[str, Any]:
    return _hub(request).replay_solar_event()


@router.post("/space-weather/refresh")
def refresh(request: Request) -> dict[str, Any]:
    hub = _hub(request)
    hub.refresh_space_weather()
    return hub.donki_state


@router.get("/link")
def get_link(request: Request) -> dict[str, Any]:
    return _hub(request).link()


@router.post("/link")
def set_link(request: Request, body: JsonBody) -> dict[str, Any]:
    return _hub(request).link(bool(body.get("up")))


@router.post("/sync")
def sync_now(request: Request) -> dict[str, Any]:
    return _hub(request).sync_all("sent by hand")


@router.get("/network")
def network(request: Request, since: int = 0) -> list[dict[str, Any]]:
    return _hub(request).net.since(since)


@router.get("/verify")
def verify(request: Request) -> dict[str, Any]:
    return _hub(request).verify()


@router.get("/db/{table}")
def table(table: str, request: Request, limit: int = 15) -> dict[str, Any]:
    """Read-only look into the spacecraft database. Device keys are masked."""
    if table not in TABLES:
        raise HTTPException(404, f"tables: {', '.join(TABLES)}")
    hub = _hub(request)
    rows = hub.store.all(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT ?", (max(1, min(limit, 200)),))
    for r in rows:
        if "device_key" in r:
            r["device_key"] = r["device_key"][:3] + "•" * 10
        for k in ("profile", "report", "body"):
            if isinstance(r.get(k), str) and len(r[k]) > 300:
                r[k] = r[k][:300] + "…"
    return {"table": table, "count": hub.store.scalar(f"SELECT COUNT(*) FROM {table}"), "rows": rows}
