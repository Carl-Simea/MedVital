"""HTTP routes of the spacecraft hub (``/hub/*``). Record format: nasa/record_format.py."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse

from medvital.hub import ai
from medvital.hub import settings as S
from medvital.hub.service import Hub
from medvital.hub.store import TABLES

router = APIRouter(prefix="/hub", tags=["hub"])
JsonBody = Annotated[dict, Body()]


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


@router.get("/status")
def status(request: Request) -> dict[str, Any]:
    hub = _hub(request)
    return {
        "sync": hub.sync_state,
        "outbox": hub.store.scalar("SELECT COUNT(*) FROM outbox"),
        "tables": hub.store.counts(),
        "donki": hub.donki_state,
        "nasaUrl": hub.nasa_url,
        "solarEvent": hub.solar_active(),
        "ai": {
            "workersAi": ai.workers_ai_enabled(),
            "workersAiModel": ai.WORKERS_AI_MODEL,
            "onboardAgent": ai.agent_model() or "rules",
        },
    }


@router.post("/pair")
def pair(request: Request, body: JsonBody) -> dict[str, Any]:
    """Docking the wearable at its charging station hands it its secret key (simulated pairing)."""
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


@router.get("/astronauts/{aid}")
def astronaut(aid: str, request: Request) -> dict[str, Any]:
    hub = _hub(request)
    _astronaut(hub, aid)
    return hub.astronaut_view(aid)


@router.get("/body/{aid}")
def body_measurements(aid: str, request: Request) -> dict[str, Any]:
    """Live values in the 3D body dashboard's keys (body-dashboard/public/parts.mjs INDICATORS)."""
    hub = _hub(request)
    _astronaut(hub, aid)
    v = hub.astronaut_view(aid)
    m: dict[str, Any] = {}
    last = v["latest"]
    if last and last["quality"] == "valid":
        m["hr.rest"] = round(last["heart_rate"])
        m["spo2.pct"] = round(last["spo2"])
    m["radiation.careerMsv"] = v["radiation"]["careerMsv"]
    if v["radiation"]["eventMsv"]:
        m["radiation.eventMsv"] = v["radiation"]["eventMsv"]
    if v["today"] and v["today"]["sleepHours"]:
        m["sleep.hours"] = v["today"]["sleepHours"]
    for lab in reversed(v["labs"]):
        m.update(lab["values"])
    return {"name": v["name"], "measurements": m, "alert": v["activeAlert"]}


@router.post("/alerts/{alert_id}/ack")
def ack(alert_id: str, request: Request) -> dict[str, Any]:
    if not _hub(request).acknowledge(alert_id):
        raise HTTPException(404, "unknown alert")
    return {"ok": True}


LAB_KEYS = {
    "urine.calciumMgDay",
    "urine.volumeL",
    "hemoglobin.gdl",
    "vitd.ngml",
    "bp.sys",
    "bp.dia",
    "temp.c",
}


@router.post("/labs/{aid}")
def labs(aid: str, request: Request, body: JsonBody) -> dict[str, Any]:
    hub = _hub(request)
    _astronaut(hub, aid)
    values = {k: float(v) for k, v in body.items() if k in LAB_KEYS and isinstance(v, (int, float))}
    if not values:
        raise HTTPException(422, f"send at least one of {sorted(LAB_KEYS)}")
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
    return _hub(request).sync_once()


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
    order = "rowid DESC"
    rows = hub.store.all(f"SELECT * FROM {table} ORDER BY {order} LIMIT ?", (max(1, min(limit, 200)),))
    for r in rows:
        if "device_key" in r:
            r["device_key"] = r["device_key"][:3] + "•" * 10
    return {"table": table, "count": hub.store.scalar(f"SELECT COUNT(*) FROM {table}"), "rows": rows}
