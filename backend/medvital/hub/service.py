"""The spacecraft hub: everything Spot 2 (Spacecraft / Cloudflare) does, in one place.

    wearable --burst--> [private network] --> Worker: double-check -> store -> rules -> reply alert
                                                 |                         |
                                          observation store          outbox --sync--> NASA (link to Earth)

Every hop is written to the network log so the Cloudflare view can draw the traffic live.
"""

from __future__ import annotations

import hmac
import json
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any

from medvital.core.module_spec import ModuleRegistry
from medvital.hub import ai, donki, rules
from medvital.hub import settings as S
from medvital.hub.store import HubStore, now_iso
from medvital.telemetry import ingest_telemetry

STATES = ("awake", "asleep", "exercise", "spacewalk")
SYNC_BATCH = 50  # same as sync.js
GENERATOR = "astronaut-app-1"


def _parse(t: str) -> datetime:
    return datetime.fromisoformat(t.replace("Z", "+00:00"))


class NetworkLog:
    """Ring buffer of hops for the Cloudflare view. ``path`` is a list of node ids."""

    def __init__(self, size: int = 600) -> None:
        self._events: deque[dict[str, Any]] = deque(maxlen=size)
        self._seq = 0
        self._lock = threading.Lock()

    def add(self, kind: str, path: list[str], status: str, label: str, **extra: Any) -> None:
        with self._lock:
            self._seq += 1
            self._events.append(
                {
                    "seq": self._seq,
                    "t": now_iso(),
                    "kind": kind,
                    "path": path,
                    "status": status,
                    "label": label,
                    **extra,
                }
            )

    def since(self, seq: int) -> list[dict[str, Any]]:
        with self._lock:
            return [e for e in self._events if e["seq"] > seq]


class Hub:
    def __init__(
        self, store: HubStore, observations: Any, registry: ModuleRegistry, nasa_url: str | None = None
    ) -> None:
        self.store = store
        self.obs = observations
        self.registry = registry
        self.nasa_url = (nasa_url or "").rstrip("/") or None
        self.net = NetworkLog()
        self._lock = threading.RLock()
        self._pending: dict[str, list[dict[str, Any]]] = {}  # alerts waiting for the next burst
        self._last_check: dict[tuple[str, str], float] = {}  # (astronaut, reason) -> monotonic time
        self.sync_state: dict[str, Any] = {
            "linkUp": None,
            "last": None,
            "confirmedTotal": 0,
            "lastError": None,
            "lastAttempt": None,
        }
        self.donki_state: dict[str, Any] = {"lastFetch": None, "source": None, "error": None}
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # ================================================================== background loops
    def start(self, sync_every: float = 2.0, donki_every: float = 1800.0) -> None:
        def loop(fn, every):
            while not self._stop.is_set():
                try:
                    fn()
                except Exception as exc:  # noqa: BLE001 - a loop must never die
                    self.net.add("error", ["worker"], "failed", f"{fn.__name__}: {exc}")
                self._stop.wait(every)

        for fn, every in ((self.sync_once, sync_every), (self.refresh_space_weather, donki_every)):
            t = threading.Thread(target=loop, args=(fn, every), daemon=True, name=f"hub-{fn.__name__}")
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()

    # ================================================================== bursts
    def handle_burst(self, p: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        aid = str(p.get("astronautId") or "")
        node = aid if aid else "unknown"
        astronaut = self.store.astronaut(aid)
        # --- secure private network: only bursts carrying that wearable's key get in -------------
        if astronaut is None or not hmac.compare_digest(
            str(p.get("deviceKey") or ""), astronaut["device_key"]
        ):
            reason = "unknown astronaut" if astronaut is None else "wrong device key"
            safe = {k: v for k, v in p.items() if k != "deviceKey"}
            self.store.run(
                "INSERT INTO rejected (time, astronaut_id, reason, payload) VALUES (?,?,?,?)",
                (now_iso(), aid or None, reason, json.dumps(safe)),
            )
            self.net.add("burst", [node, "tunnel"], "blocked", f"Blocked burst from {node}: {reason}")
            return 401, {"error": reason, "alert": None}
        missing = [k for k in ("time", "heartRate", "spo2", "state", "doseRate", "totalDose") if k not in p]
        if missing or p.get("state") not in STATES:
            reason = (
                f"malformed burst (missing {missing})" if missing else f"unknown state {p.get('state')!r}"
            )
            self.store.run(
                "INSERT INTO rejected (time, astronaut_id, reason, payload) VALUES (?,?,?,?)",
                (now_iso(), aid, reason, json.dumps({k: v for k, v in p.items() if k != "deviceKey"})),
            )
            self.net.add("burst", [aid, "tunnel", "worker"], "failed", f"{aid}: {reason}")
            return 400, {"error": reason, "alert": None}

        t0 = time.perf_counter()
        with self._lock:
            history = self.store.recent_bursts(aid, 200)
            check = rules.double_check(p, history[-1] if history else None)
            burst = {**p, "quality": check.quality, "checkNote": check.note or None}
            burst_id = self.store.add_burst(burst)
            history = self.store.recent_bursts(aid, 200)
            self._to_observations(aid, burst_id, burst)
            self.store.to_outbox(
                self._record(
                    f"{aid}-r{burst_id}",
                    "reading",
                    aid,
                    p["time"],
                    {
                        "heartRate": p["heartRate"],
                        "spo2": p["spo2"],
                        "state": p["state"],
                        "doseRate": p["doseRate"],
                        "totalDose": p["totalDose"],
                        "quality": check.quality,
                        "checkNote": check.note or None,
                        "seq": p.get("seq"),
                        "scenario": p.get("scenario"),
                    },
                )
            )
            decisions = rules.evaluate(history, astronaut["profile"], self.solar_active() is not None)
            for d in decisions:
                self._raise_alert(aid, d)
            day_done = len(history) and self.store.burst_count(aid) % S.BURSTS_PER_MISSION_DAY == 0
            delivered = self._next_alert(aid)
            self.store.set_burst_alert(burst_id, delivered["code"] if delivered else None)
        if day_done:
            threading.Thread(target=self.daily_summary, args=(aid,), daemon=True).start()

        ms = round((time.perf_counter() - t0) * 1000, 1)
        status = "flagged" if check.quality != "valid" else "ok"
        self.net.add(
            "burst",
            [aid, "tunnel", "worker", "d1"],
            status,
            f"{aid} burst #{p.get('seq')} HR {p['heartRate']:.0f} SpO2 {p['spo2']:.0f} "
            f"{p['doseRate']:.0f} µSv/h ({p['state']})" + (f" · {check.note}" if check.note else ""),
            ms=ms,
        )
        if delivered:
            self.net.add(
                "alert",
                ["worker", "tunnel", aid],
                "alert",
                f"{delivered['code']} → {aid}",
                code=delivered["code"],
            )
        wx = self.solar_active()
        return 200, {
            "accepted": True,
            "burstId": burst_id,
            "quality": check.quality,
            "checkNote": check.note or None,
            "alert": delivered["code"] if delivered else None,
            "alertId": delivered["id"] if delivered else None,
            "message": (delivered.get("ai_message") or delivered["message"]) if delivered else None,
            "spaceWeather": {"solarEventActive": wx is not None, "summary": wx["summary"] if wx else None},
        }

    def _record(self, rid: str, rtype: str, aid: str, t: str, data: dict[str, Any]) -> dict[str, Any]:
        """One record in the shared format (nasa/record_format.py)."""
        return {"id": rid, "type": rtype, "astronautId": aid, "time": t, "data": data}

    def _to_observations(self, aid: str, burst_id: int, b: dict[str, Any]) -> None:
        """Mirror the burst into the provenance-labelled observation store (labelled simulated)."""
        base = {
            "device_id": f"WEARABLE-{aid}",
            "crew_id": aid,
            "timestamp": b["time"],
            "source": "astronaut_app",
            "quality": b["quality"],
            "synthetic": True,
            "generator_version": GENERATOR,
            "seed": 0,
        }
        fields = (
            ("cardiovascular", "heart_rate", "heartRate", "bpm"),
            ("cardiovascular", "spo2", "spo2", "%"),
            ("radiation", "dose_equivalent_rate", "doseRate", "uSv/h"),
            ("radiation", "cumulative_dose_equivalent", "totalDose", "mSv"),
        )
        events = [
            {
                **base,
                "event_id": f"B{burst_id}-{ind}",
                "domain": dom,
                "indicator": ind,
                "value": float(b[key]),
                "unit": unit,
            }
            for dom, ind, key, unit in fields
            if isinstance(b.get(key), (int, float)) and b[key] >= 0
        ]
        ingest_telemetry(self.obs, self.registry, events, max_future_skew_seconds=86400)

    # ================================================================== alerts
    def _raise_alert(self, aid: str, d: rules.Decision) -> None:
        if d.code == rules.CHECK_VITALS:
            key, now = (aid, d.reason), time.monotonic()
            if now - self._last_check.get(key, -1e9) < S.CHECK_VITALS_COOLDOWN_S:
                return
            self._last_check[key] = now
        if d.code == rules.RETURN_NOW:
            # RETURN_NOW repeats on every burst while it holds; store one row per spacewalk + reason.
            active = self.store.one(
                "SELECT * FROM alerts WHERE astronaut_id=? AND code=? AND status='active'", (aid, d.code)
            )
            if active:
                self._queue(aid, active)
                return
        alert = {
            "id": f"{aid}-a{uuid.uuid4().hex[:10]}",
            "astronaut_id": aid,
            "code": d.code,
            "reason": d.reason,
            "message": d.message,
            "ai_message": None,
            "ai_source": "template",
            "time": now_iso(),
            "status": "active",
        }
        self.store.run(
            "INSERT INTO alerts (id, astronaut_id, code, reason, message, ai_source, time, status)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (alert["id"], aid, d.code, d.reason, d.message, "template", alert["time"], "active"),
        )
        self.store.to_outbox(
            self._record(
                alert["id"],
                "alert",
                aid,
                alert["time"],
                {"code": d.code, "message": d.message, "reason": d.reason, "facts": d.facts},
            )
        )
        self._queue(aid, alert)
        self.net.add(
            "rule", ["worker", "d1", "outbox"], "alert", f"Rule fired: {d.code} for {aid} ({d.reason})"
        )
        if ai.workers_ai_enabled():
            threading.Thread(target=self._reword_alert, args=(alert,), daemon=True).start()

    def _reword_alert(self, alert: dict[str, Any]) -> None:
        self.net.add("ai", ["worker", "ai"], "info", f"Workers AI explaining {alert['code']}")
        text, source, note = ai.reword(alert["message"], "alert")
        self.store.run(
            "UPDATE alerts SET ai_message=?, ai_source=? WHERE id=?",
            (text if source != "template" else None, source, alert["id"]),
        )
        self.net.add("ai", ["ai", "agent"], "ok" if source != "template" else "info", note)

    def _queue(self, aid: str, alert: dict[str, Any]) -> None:
        q = self._pending.setdefault(aid, [])
        if all(a["id"] != alert["id"] for a in q):
            q.append(alert)

    def _next_alert(self, aid: str) -> dict[str, Any] | None:
        """The most urgent waiting alert. RETURN_NOW stays queued until the astronaut is back inside."""
        q = self._pending.get(aid, [])
        latest = self.store.recent_bursts(aid, 1)
        inside = bool(latest) and latest[-1]["state"] != "spacewalk"
        if inside:  # back inside: close RETURN_NOW
            self.store.run(
                "UPDATE alerts SET status='resolved' WHERE astronaut_id=? AND code=? AND status='active'",
                (aid, rules.RETURN_NOW),
            )
            q[:] = [a for a in q if a["code"] != rules.RETURN_NOW]
        if not q:
            return None
        order = {rules.RETURN_NOW: 0, rules.CHECK_VITALS: 1, rules.INFO: 2}
        q.sort(key=lambda a: order.get(a["code"], 9))
        top = q[0]
        if top["code"] != rules.RETURN_NOW:
            q.pop(0)
            if top["code"] == rules.INFO:  # an INFO buzz is done once it reaches the wearable
                self.store.run("UPDATE alerts SET status='delivered' WHERE id=?", (top["id"],))
        fresh = self.store.one("SELECT * FROM alerts WHERE id=?", (top["id"],))
        return fresh or top

    def acknowledge(self, alert_id: str) -> bool:
        row = self.store.one("SELECT * FROM alerts WHERE id=?", (alert_id,))
        if not row:
            return False
        if row["code"] != rules.RETURN_NOW:  # RETURN_NOW only ends when the astronaut is back inside
            self.store.run("UPDATE alerts SET status='acknowledged' WHERE id=?", (alert_id,))
        return True

    # ================================================================== daily summary, labs, agent
    def daily_summary(self, aid: str) -> dict[str, Any] | None:
        astronaut = self.store.astronaut(aid)
        if astronaut is None:
            return None
        n = self.store.burst_count(aid)
        day = max(1, -(-n // S.BURSTS_PER_MISSION_DAY))
        bursts = self.store.recent_bursts(aid, S.BURSTS_PER_MISSION_DAY)
        if not bursts:
            return None
        since = bursts[0]["received_at"]
        alerts = (
            self.store.scalar(
                "SELECT COUNT(*) FROM alerts WHERE astronaut_id=? AND time>=? AND code!='INFO'", (aid, since)
            )
            or 0
        )
        facts = rules.day_facts(bursts, astronaut["profile"], alerts)
        template = rules.summary_text(astronaut["name"], day, facts) + " " + rules.exercise_tip(facts)
        text, source, note = ai.reword(template, "daily health summary")
        sid = f"{aid}-s{uuid.uuid4().hex[:10]}"
        t = now_iso()
        self.store.run(
            "INSERT INTO summaries (id, astronaut_id, mission_day, time, text, facts, ai_source, check_note)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (sid, aid, day, t, text, json.dumps(facts), source, note),
        )
        self.store.to_outbox(
            self._record(
                sid,
                "summary",
                aid,
                t,
                {"text": text, "missionDay": day, "facts": facts, "wordedBy": source, "check": note},
            )
        )
        self.net.add(
            "summary",
            ["worker", "ai", "agent", "ai", "d1", "outbox"],
            "ok",
            f"Daily summary for {aid}, mission day {day} ({source})",
        )
        self._raise_alert(
            aid, rules.Decision(rules.INFO, "summary", f"Your mission day {day} summary is ready.", {})
        )
        if facts["exerciseMinutes"] < facts["exerciseTargetMinutes"]:
            self._raise_alert(aid, rules.Decision(rules.INFO, "exercise", rules.exercise_tip(facts), facts))
        return {"id": sid, "missionDay": day, "text": text, "facts": facts, "wordedBy": source, "check": note}

    def add_labs(self, aid: str, values: dict[str, float]) -> dict[str, Any]:
        lid, t = f"{aid}-l{uuid.uuid4().hex[:10]}", now_iso()
        self.store.run(
            "INSERT INTO labs (id, astronaut_id, time, ivalues) VALUES (?,?,?,?)",
            (lid, aid, t, json.dumps(values)),
        )
        self.store.to_outbox(self._record(lid, "lab", aid, t, {"values": values}))
        self.net.add("lab", [aid, "tunnel", "worker", "d1", "outbox"], "ok", f"Lab results from {aid}")
        return {"id": lid, "time": t, "values": values}

    def ask(self, aid: str, question: str) -> dict[str, Any]:
        self.net.add("agent", [aid, "tunnel", "agent"], "info", f"{aid} asks the onboard agent")
        text, source = ai.answer(question, self.astronaut_view(aid))
        self.store.run(
            "INSERT INTO agent_log (time, astronaut_id, question, answer, source) VALUES (?,?,?,?,?)",
            (now_iso(), aid, question[:500], text[:2000], source),
        )
        self.net.add("agent", ["agent", "tunnel", aid], "ok", f"Agent answered {aid} ({source})")
        return {"answer": text, "source": source}

    # ================================================================== space weather
    def solar_active(self) -> dict[str, Any] | None:
        return self.store.one(
            "SELECT * FROM space_weather WHERE kind='SEP' AND active_until > ? "
            "ORDER BY active_until DESC LIMIT 1",
            (now_iso(),),
        )

    def replay_solar_event(self) -> dict[str, Any]:
        rec = donki.REPLAY_EVENT
        eid, etime, summary, link = donki.describe("SEP", rec)
        until = (
            (datetime.now(UTC) + timedelta(seconds=S.SOLAR_EVENT_ACTIVE_S)).isoformat().replace("+00:00", "Z")
        )
        rid = f"replay-{uuid.uuid4().hex[:8]}"
        self.store.run(
            "INSERT INTO space_weather (id, kind, event_time, received_at, active_until, summary, link,"
            " source, replay) VALUES (?,?,?,?,?,?,?,?,1)",
            (rid, "SEP", etime, now_iso(), until, f"REPLAY of {eid}: {summary}", link, "NASA DONKI (replay)"),
        )
        self.net.add("donki", ["donki", "link", "d1", "worker"], "alert", f"Solar event replayed: {eid}")
        for a in self.store.astronauts():
            self.store.to_outbox(
                self._record(
                    f"{a['id']}-w{rid}",
                    "alert",
                    a["id"],
                    now_iso(),
                    {
                        "code": "INFO",
                        "reason": "space_weather",
                        "message": f"Space weather: replay of DONKI {eid}. {summary}",
                    },
                )
            )
        return {"id": rid, "event": eid, "activeUntil": until, "summary": summary, "link": link}

    def refresh_space_weather(self) -> None:
        added = 0
        try:
            for kind in donki.KINDS:
                recs, base = donki.fetch(kind)
                for r in recs:
                    try:
                        eid, etime, summary, link = donki.describe(kind, r)
                    except (KeyError, TypeError):
                        continue
                    added += (
                        self.store.run(
                            "INSERT OR IGNORE INTO space_weather (id, kind, event_time, received_at,"
                            " active_until,"
                            " summary, link, source, replay) VALUES (?,?,?,?,NULL,?,?,?,0)",
                            (eid, kind, etime, now_iso(), summary, link, "NASA DONKI"),
                        )
                        and 1
                    )
            self.donki_state = {"lastFetch": now_iso(), "source": base, "error": None}
            self.net.add("donki", ["donki", "link", "d1"], "ok", f"DONKI pulled ({base})")
        except Exception as exc:  # noqa: BLE001 - offline is fine: the replay button still works
            self.donki_state = {"lastFetch": now_iso(), "source": None, "error": str(exc)[:200]}
            self.net.add(
                "donki",
                ["d1", "link", "donki"],
                "failed",
                "DONKI unreachable (offline?). Replay still works.",
            )

    # ================================================================== link to Earth
    def _nasa(self, method: str, path: str, body: Any = None, timeout: float = 5.0) -> tuple[int | None, Any]:
        if not self.nasa_url:
            return None, None
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.nasa_url + path, data=data, method=method, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (operator-supplied URL)
                return r.status, json.loads(r.read().decode() or "null")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode() or "null")
            except ValueError:
                return e.code, None
        except (urllib.error.URLError, OSError, ValueError):
            return None, None

    def sync_once(self) -> dict[str, Any]:
        """Port of spacecraft-sync/sync.js: send up to 50 oldest outbox records, delete only confirmed ids."""
        rows = self.store.outbox_batch(SYNC_BATCH)
        if not rows:
            return {"linkUp": self.sync_state["linkUp"], "sent": 0, "confirmed": 0}
        if not self.nasa_url:
            self.sync_state.update(linkUp=None, lastError="NASA_URL not set", lastAttempt=now_iso())
            return {"linkUp": None, "sent": 0, "confirmed": 0, "problem": "NASA_URL not set"}
        records = [json.loads(r["body"]) for r in rows]
        t0 = time.perf_counter()
        status, answer = self._nasa("POST", "/batch", {"records": records}, timeout=10)
        ms = round((time.perf_counter() - t0) * 1000)
        self.sync_state["lastAttempt"] = now_iso()
        if status != 200 or not isinstance(answer, dict) or not isinstance(answer.get("saved"), list):
            problem = (
                "link down (NASA answered 503)"
                if status == 503
                else "NASA unreachable"
                if status is None
                else f"NASA answered HTTP {status}"
            )
            self.sync_state.update(
                linkUp=False, lastError=problem, last={"sent": len(records), "confirmed": 0, "at": now_iso()}
            )
            self.net.add(
                "sync",
                ["outbox", "link", "nasa"],
                "failed",
                f"Batch of {len(records)} not delivered: {problem}. Kept in the outbox.",
                ms=ms,
            )
            return {"linkUp": False, "sent": len(records), "confirmed": 0, "problem": problem}
        sent_ids = {r["id"] for r in records}
        confirmed = [str(i) for i in answer["saved"] if str(i) in sent_ids]
        n = self.store.confirm(confirmed)
        self.sync_state.update(
            linkUp=True,
            lastError=None,
            last={"sent": len(records), "confirmed": len(confirmed), "at": now_iso()},
        )
        self.sync_state["confirmedTotal"] += n
        self.net.add(
            "sync",
            ["outbox", "link", "nasa"],
            "ok",
            f"Batch of {len(records)} sent, NASA confirmed {len(confirmed)}",
            ms=ms,
            count=len(records),
        )
        self.net.add("ack", ["nasa", "link", "outbox"], "ok", f"NASA saved {len(confirmed)} ids")
        return {"linkUp": True, "sent": len(records), "confirmed": len(confirmed)}

    def link(self, up: bool | None = None) -> dict[str, Any]:
        if up is None:
            status, ans = self._nasa("GET", "/link")
        else:
            status, ans = self._nasa("POST", "/link", {"up": bool(up)})
            self.net.add(
                "link", ["link"], "ok" if up else "failed", f"Link to Earth switched {'UP' if up else 'DOWN'}"
            )
        reachable = status == 200 and isinstance(ans, dict)
        return {"nasaUrl": self.nasa_url, "reachable": reachable, "up": ans.get("up") if reachable else None}

    # ================================================================== views
    def astronaut_view(self, aid: str) -> dict[str, Any]:
        a = self.store.astronaut(aid)
        if a is None:
            raise KeyError(aid)
        prof = a["profile"]
        bursts = self.store.recent_bursts(aid, 120)
        latest = bursts[-1] if bursts else None
        total = latest["total_dose"] if latest else 0.0
        eva, eva_n = rules.eva_dose(bursts)
        wx = self.solar_active()
        active = self.store.one(
            "SELECT * FROM alerts WHERE astronaut_id=? ORDER BY time DESC LIMIT 1", (aid,)
        )
        last_summary = self.store.one(
            "SELECT * FROM summaries WHERE astronaut_id=? ORDER BY time DESC LIMIT 1", (aid,)
        )
        if last_summary:
            last_summary["facts"] = json.loads(last_summary["facts"])
        n = self.store.burst_count(aid)
        today_n = n % S.BURSTS_PER_MISSION_DAY or (S.BURSTS_PER_MISSION_DAY if n else 0)
        today = rules.day_facts(bursts[-today_n:], prof, 0) if today_n else None
        career = prof["prior_career_msv"] + total
        event_dose = 0.0
        if wx:
            during = [b for b in bursts if b["received_at"] >= wx["received_at"]]
            if during:
                event_dose = max(0.0, during[-1]["total_dose"] - during[0]["total_dose"])
        labs = self.store.all("SELECT * FROM labs WHERE astronaut_id=? ORDER BY time DESC LIMIT 5", (aid,))
        for lab in labs:
            lab["values"] = json.loads(lab.pop("ivalues"))
        return {
            "id": aid,
            "name": a["name"],
            "role": a["role"],
            "profile": prof,
            "latest": latest,
            "bursts": bursts,
            "burstCount": n,
            "radiation": {
                "missionMsv": round(total, 3),
                "careerMsv": round(career, 2),
                "careerPct": round(100 * career / S.LIMITS["career_msv"].value, 2),
                "evaMsv": round(eva, 3),
                "evaBudgetMsv": S.LIMITS["eva_msv"].value,
                "evaPct": round(100 * eva / S.LIMITS["eva_msv"].value, 1),
                "evaMinutes": eva_n * S.MISSION_MINUTES_PER_BURST,
                "eventMsv": round(event_dose, 3),
                "eventPct": round(100 * event_dose / S.LIMITS["solar_event_msv"].value, 2),
            },
            "spaceWeather": {
                "active": wx,
                "recent": self.store.all("SELECT * FROM space_weather ORDER BY event_time DESC LIMIT 6"),
            },
            "activeAlert": active,
            "lastSummary": last_summary,
            "today": today,
            "labs": labs,
            "alerts": self.store.all(
                "SELECT * FROM alerts WHERE astronaut_id=? ORDER BY time DESC LIMIT 10", (aid,)
            ),
        }

    def crew(self) -> list[dict[str, Any]]:
        out = []
        for a in self.store.astronauts():
            v = self.astronaut_view(a["id"])
            v["bursts"] = v["bursts"][-40:]
            out.append(v)
        return out

    def nasa_stats(self) -> dict[str, Any] | None:
        status, ans = self._nasa("GET", "/stats")
        return ans if status == 200 else None

    def verify(self) -> dict[str, Any]:
        """Double-check every hop: what the wearables sent, what the hub kept, what NASA has."""
        nasa = self.nasa_stats()
        rows = []
        for a in self.store.astronauts():
            aid = a["id"]
            bursts = self.store.burst_count(aid)
            max_seq = self.store.scalar("SELECT MAX(seq) FROM bursts WHERE astronaut_id=?", (aid,)) or 0
            flagged = (
                self.store.scalar(
                    "SELECT COUNT(*) FROM bursts WHERE astronaut_id=? AND quality!='valid'", (aid,)
                )
                or 0
            )
            observations = len(self.obs.query(subject_id=aid, limit=1_000_000))
            created = self.store.scalar("SELECT COUNT(*) FROM records WHERE astronaut_id=?", (aid,)) or 0
            by_type = {
                r["type"]: r["n"]
                for r in self.store.all(
                    "SELECT type, COUNT(*) n FROM records WHERE astronaut_id=? GROUP BY type", (aid,)
                )
            }
            pending = (
                self.store.scalar(
                    "SELECT COUNT(*) FROM outbox o JOIN records r ON r.id=o.id WHERE r.astronaut_id=?", (aid,)
                )
                or 0
            )
            synced = (
                self.store.scalar(
                    "SELECT COUNT(*) FROM synced s JOIN records r ON r.id=s.id WHERE r.astronaut_id=?", (aid,)
                )
                or 0
            )
            at_nasa = (nasa or {}).get("by_astronaut", {}).get(aid)
            rows.append(
                {
                    "astronautId": aid,
                    "wearableSent": max_seq,
                    "hubBursts": bursts,
                    "missingBursts": max(0, max_seq - bursts),
                    "flagged": flagged,
                    "observations": observations,
                    "recordsCreated": created,
                    "byType": by_type,
                    "outboxPending": pending,
                    "confirmedByNasa": synced,
                    "atNasa": at_nasa,
                    "nasaByType": (nasa or {}).get("by_astronaut_and_type", {}).get(aid),
                    "ok": at_nasa is not None and created == synced + pending and at_nasa >= synced,
                }
            )
        return {
            "rows": rows,
            "nasaReachable": nasa is not None,
            "nasaTotal": (nasa or {}).get("total"),
            "outbox": self.store.scalar("SELECT COUNT(*) FROM outbox") or 0,
            "rejectedBursts": self.store.scalar("SELECT COUNT(*) FROM rejected") or 0,
        }
