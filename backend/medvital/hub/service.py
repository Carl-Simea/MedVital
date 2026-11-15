"""The spacecraft hub: everything Spot 2 (Spacecraft / Cloudflare) does, in one place.

    wearables --burst every second--> [private network] --> Worker: double-check -> store -> rules
                                                                  |                      |
                                                           observation store      outbox --(day end / urgent)--> NASA

One real minute is one mission day. At the end of each mission day the hub writes daily summaries and sends
the day's records to NASA in one batch; RETURN_NOW and CHECK_VITALS alerts go immediately. During a
scheduled blackout, or while the link switch is down, records wait in the outbox. Every hop is written to the
network log so the Cloudflare view can draw it.
"""

from __future__ import annotations

import hmac
import json
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import uuid
import zlib
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from medvital.core.module_spec import ModuleRegistry
from medvital.hub import ai, donki, rules
from medvital.hub import mission as M
from medvital.hub import settings as S
from medvital.hub.simulator import CrewSimulator, preflight_values
from medvital.hub.store import HubStore, now_iso
from medvital.telemetry import ingest_telemetry

STATES = ("awake", "asleep", "exercise", "spacewalk")
SYNC_BATCH = 200
GENERATOR = "medvital-crew-sim-2"
URGENT = (rules.RETURN_NOW, rules.CHECK_VITALS)


class NetworkLog:
    """Ring buffer of hops for the Cloudflare view. ``path`` is a list of node ids."""

    def __init__(self, size: int = 1500) -> None:
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

    def since(self, seq: int, limit: int = 400) -> list[dict[str, Any]]:
        with self._lock:
            return [e for e in self._events if e["seq"] > seq][-limit:]


class Hub:
    def __init__(
        self,
        store: HubStore,
        observations: Any,
        registry: ModuleRegistry,
        nasa_url: str | None = None,
        observations_path: str | Path | None = None,
        cloudflare_url: str | None = None,
        cloudflare_key: str | None = None,
    ) -> None:
        self.store = store
        self.obs = observations
        self.obs_path = str(observations_path) if observations_path else None
        self.registry = registry
        self.nasa_url = (nasa_url or "").rstrip("/") or None
        # Cloudflare link to Earth (cloudflare/ Worker + D1). When set, the outbox goes to the Worker and
        # NASA pulls from it; the key is read from the environment only, never from a file in the repo.
        self.cf_url = (cloudflare_url if cloudflare_url is not None else S.CLOUDFLARE_URL).rstrip("/") or None
        self.cf_key = cloudflare_key if cloudflare_key is not None else S.CLOUDFLARE_KEY
        self.net = NetworkLog()
        self._lock = threading.RLock()
        self._pending: dict[str, list[dict[str, Any]]] = {}
        self._last_check: dict[tuple[str, str], float] = {}
        self.sync_state: dict[str, Any] = {
            "linkUp": None,
            "last": None,
            "confirmedTotal": 0,
            "lastError": None,
            "lastAttempt": None,
            "lastDayEnd": None,
            "history": [],
        }
        self.donki_state: dict[str, Any] = {"lastFetch": None, "source": None, "error": None}
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        start = store.meta("mission_start_real")
        if start is None:
            start = store.meta("mission_start_real", repr(time.time()))
        self.clock = M.MissionClock(float(start))
        self.sim = CrewSimulator(self)
        self._init_mission()

    # ================================================================== mission setup
    def _init_mission(self) -> None:
        if self.store.meta("mission_initialised"):
            return
        events = M.crew_plan()
        for c in S.CREW:
            report = None
            if c.report and (S.REPORTS / f"{c.report}.txt").exists():
                report = (S.REPORTS / f"{c.report}.txt").read_text(encoding="utf-8")
            self.store.add_astronaut(c.to_json(), report)
            events += M.plan_for(c.astronaut_id, c.exercise_hour)
            self._profile_record(c.astronaut_id)
        self._insert_events(events)
        self.store.meta("mission_initialised", now_iso())

    def _insert_events(self, events: list[dict[str, Any]]) -> None:
        self.store.many(
            "INSERT INTO events (m_start, m_end, kind, astronaut_id, title, detail, source, link, sw_type)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (
                    e["m_start"],
                    e["m_end"],
                    e["kind"],
                    e.get("astronaut_id"),
                    e["title"],
                    e.get("detail"),
                    e["source"],
                    e.get("link"),
                    e.get("sw_type"),
                )
                for e in events
            ],
        )
        rows = [
            self._record(
                f"ev-{e.get('astronaut_id') or 'crew'}-{int(e['m_start'])}-{e['kind']}-"
                f"{zlib.crc32(e['title'].encode()) % 10_000}",
                "event",
                e.get("astronaut_id") or "crew",
                now_iso(),
                {
                    k: e.get(k)
                    for k in ("m_start", "m_end", "kind", "title", "detail", "source", "link", "sw_type")
                },
            )
            for e in events
            if e["kind"] not in ("sleep", "exercise")
        ]
        for r in rows:
            self.store.to_outbox(r)

    def _profile_record(self, aid: str) -> None:
        a = self.store.astronaut(aid)
        self.store.to_outbox(
            self._record(
                f"{aid}-profile", "profile", aid, now_iso(), {"profile": a["profile"], "report": a["report"]}
            )
        )
        self.store.add_tests(aid, 0.0, preflight_values(a["profile"]), "pre-flight", "pre-flight report")

    def add_astronaut(self, profile: dict[str, Any], report: str | None) -> dict[str, Any]:
        """Sign-up: a new astronaut with their pre-flight baseline. The rest of their data is simulated."""
        base = re.sub(r"[^a-z0-9]+", "-", profile["name"].lower()).strip("-")[:24] or "crew"
        aid = profile.get("astronaut_id") or base
        n = 2
        while self.store.astronaut(aid):
            aid, n = f"{base}-{n}", n + 1
        profile = {**profile, "astronaut_id": aid}
        self.store.add_astronaut(profile, report)
        now = self.clock.minute()
        self._insert_events(
            M.plan_for(aid, float(profile.get("exercise_hour", 17.0)), from_day=M.day_of(now))
        )
        self._profile_record(aid)
        self.net.add(
            "pair", [aid, "tunnel", "worker", "d1"], "ok", f"New astronaut {profile['name']} joined ({aid})"
        )
        return self.store.astronaut(aid)

    # ================================================================== background loops
    def start(self) -> None:
        def loop(fn, every):
            while not self._stop.is_set():
                t0 = time.time()
                try:
                    fn()
                except Exception as exc:  # noqa: BLE001 - a loop must never die
                    self.net.add("error", ["worker"], "failed", f"{fn.__name__}: {exc}")
                self._stop.wait(max(0.05, every - (time.time() - t0)))

        for fn, every in (
            (self.tick, S.BURST_SECONDS),
            (self.sync_tick, 1.0),
            (self.refresh_space_weather, 1800.0),
        ):
            t = threading.Thread(target=loop, args=(fn, every), daemon=True, name=f"hub-{fn.__name__}")
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()

    def tick(self) -> None:
        """One second: every worn wearable sends a burst; scheduled tests run; a day may end."""
        m = self.clock.minute()
        last = float(self.store.meta("last_tick_minute") or m)
        self.sim.tick(m)
        if int(last // M.DAY_MIN) != int(m // M.DAY_MIN):
            self.end_of_day(int(last // M.DAY_MIN) + 1)
        self.store.meta("last_tick_minute", repr(m))

    # ================================================================== bursts
    def handle_burst(self, p: dict[str, Any], simulated: bool = False) -> tuple[int, dict[str, Any]]:
        aid = str(p.get("astronautId") or "")
        node = aid if aid else "unknown"
        astronaut = self.store.astronaut(aid)
        if astronaut is None or not hmac.compare_digest(
            str(p.get("deviceKey") or ""), astronaut["device_key"]
        ):
            reason = "unknown astronaut" if astronaut is None else "wrong device key"
            safe = {k: v for k, v in p.items() if k != "deviceKey"}
            self.store.run(
                "INSERT INTO rejected (time, astronaut_id, reason, payload) VALUES (?,?,?,?)",
                (now_iso(), aid or None, reason, json.dumps(safe)),
            )
            self.net.add(
                "burst",
                [node, "tunnel"],
                "blocked",
                f"Blocked a device claiming to be {node}: {reason}",
                astronaut=aid,
            )
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
            self.net.add("burst", [aid, "tunnel", "worker"], "failed", f"{aid}: {reason}", astronaut=aid)
            return 400, {"error": reason, "alert": None}
        if p.get("missionMinute") is None:
            p = {**p, "missionMinute": round(self.clock.minute(), 2)}

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
                        "respRate": p.get("respRate"),
                        "skinTemp": p.get("skinTemp"),
                        "quality": check.quality,
                        "checkNote": check.note or None,
                        "seq": p.get("seq"),
                        "radRef": p.get("radRef"),
                        "missionMinute": p["missionMinute"],
                    },
                )
            )
            solar = self.solar_active() is not None or M.sep_active(p["missionMinute"]) is not None
            for d in rules.evaluate(history, astronaut["profile"], solar):
                self._raise_alert(aid, d, p["missionMinute"])
            delivered = self._next_alert(aid)
            self.store.set_burst_alert(burst_id, delivered["code"] if delivered else None)

        status = "flagged" if check.quality != "valid" else "ok"
        self.net.add(
            "burst",
            [aid, "tunnel", "worker", "d1"],
            status,
            f"{aid} #{p.get('seq')} HR {p['heartRate']:.0f} SpO2 {p['spo2']:.0f} "
            f"{p['doseRate']:.0f} µSv/h ({p['state']})" + (f" · {check.note}" if check.note else ""),
            astronaut=aid,
            bytes=len(json.dumps(p)),
        )
        if delivered:
            self.net.add(
                "alert",
                ["worker", "tunnel", aid],
                "alert",
                f"{delivered['code']} → {aid}",
                code=delivered["code"],
                astronaut=aid,
            )
        wx = self.solar_active()
        sep = M.sep_active(p["missionMinute"])
        return 200, {
            "accepted": True,
            "burstId": burst_id,
            "quality": check.quality,
            "checkNote": check.note or None,
            "alert": delivered["code"] if delivered else None,
            "alertId": delivered["id"] if delivered else None,
            "message": (delivered.get("ai_message") or delivered["message"]) if delivered else None,
            "spaceWeather": {
                "solarEventActive": bool(wx or sep),
                "summary": wx["summary"] if wx else (sep[2] if sep else None),
            },
        }

    def _record(self, rid: str, rtype: str, aid: str, t: str, data: dict[str, Any]) -> dict[str, Any]:
        """One record in the shared format (nasa/record_format.py), stamped with mission time."""
        return {
            "id": rid,
            "type": rtype,
            "astronautId": aid,
            "time": t,
            "mission": M.describe(self.clock.minute()),
            "data": data,
        }

    def _to_observations(self, aid: str, burst_id: int, b: dict[str, Any]) -> None:
        """Mirror the burst into the provenance-labelled observation store (labelled simulated)."""
        base = {
            "device_id": f"WEARABLE-{aid}"[:64],
            "crew_id": aid,
            "timestamp": b["time"],
            "source": "crew_sim",
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

    # ================================================================== measurements (tests, labs)
    def add_measurements(
        self, aid: str, m: float, values: dict[str, float], origin: str, source: str
    ) -> dict:
        self.store.add_tests(aid, m, values, origin, source)
        rid = f"{aid}-t{uuid.uuid4().hex[:10]}"
        self.store.to_outbox(
            self._record(
                rid,
                "lab" if origin == "entered" else "test",
                aid,
                now_iso(),
                {"values": values, "origin": origin, "source": source, "missionMinute": round(m, 2)},
            )
        )
        path = [aid, "tunnel", "worker", "d1", "outbox"] if origin == "entered" else ["worker", "d1"]
        self.net.add("test", path, "ok", f"{aid}: {source} ({', '.join(values)[:80]})", astronaut=aid)
        return {"id": rid, "values": values, "origin": origin, "source": source}

    def add_labs(self, aid: str, values: dict[str, float]) -> dict[str, Any]:
        return self.add_measurements(aid, self.clock.minute(), values, "entered", "entered by the astronaut")

    # ================================================================== alerts
    def _raise_alert(self, aid: str, d: rules.Decision, m: float | None = None) -> None:
        m = self.clock.minute() if m is None else m
        if d.code == rules.CHECK_VITALS:
            key, now = (aid, d.reason), time.monotonic()
            if now - self._last_check.get(key, -1e9) < S.CHECK_VITALS_COOLDOWN_S:
                return
            self._last_check[key] = now
        if d.code == rules.RETURN_NOW:
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
            "INSERT INTO alerts (id, astronaut_id, code, reason, message, ai_source, time, mission_minute,"
            " status) VALUES (?,?,?,?,?,?,?,?,?)",
            (alert["id"], aid, d.code, d.reason, d.message, "template", alert["time"], m, "active"),
        )
        self.store.to_outbox(
            self._record(
                alert["id"],
                "alert",
                aid,
                alert["time"],
                {
                    "code": d.code,
                    "message": d.message,
                    "reason": d.reason,
                    "facts": d.facts,
                    "missionMinute": round(m, 2),
                },
            ),
            urgent=d.code in URGENT,
        )
        self._queue(aid, alert)
        self.net.add(
            "rule",
            ["worker", "d1", "outbox"],
            "alert",
            f"Rule fired: {d.code} for {aid} ({d.reason})",
            astronaut=aid,
        )
        if d.code in URGENT:
            self._follow_up(aid, d, m)
        if ai.workers_ai_enabled():
            threading.Thread(target=self._reword_alert, args=(alert,), daemon=True).start()

    def _follow_up(self, aid: str, d: rules.Decision, m: float) -> None:
        """Alerts create follow-ups NASA's flight surgeon will see as upcoming events."""
        what = "Re-check vitals" if d.code == rules.CHECK_VITALS else "Post-EVA radiation review"
        events = [
            {
                "m_start": m + 6 * 60,
                "m_end": m + 6 * 60 + 15,
                "kind": "followup",
                "astronaut_id": aid,
                "title": what,
                "detail": d.message[:200],
                "source": f"follow-up after {d.code}",
                "link": None,
            },
            {
                "m_start": (M.day_of(m)) * M.DAY_MIN - 30,
                "m_end": M.day_of(m) * M.DAY_MIN,
                "kind": "followup",
                "astronaut_id": aid,
                "title": "Flight surgeon review",
                "detail": f"Review {d.code} ({d.reason})",
                "source": f"follow-up after {d.code}",
                "link": None,
            },
        ]
        self._insert_events(events)

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
        q = self._pending.get(aid, [])
        latest = self.store.recent_bursts(aid, 1)
        if latest and latest[-1]["state"] != "spacewalk":
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
            if top["code"] == rules.INFO:
                self.store.run("UPDATE alerts SET status='delivered' WHERE id=?", (top["id"],))
        return self.store.one("SELECT * FROM alerts WHERE id=?", (top["id"],)) or top

    def acknowledge(self, alert_id: str) -> bool:
        row = self.store.one("SELECT * FROM alerts WHERE id=?", (alert_id,))
        if not row:
            return False
        if row["code"] == rules.RETURN_NOW:
            self.sim.sync_crew()
            w = self.sim.wearers.get(row["astronaut_id"])
            if w is not None:  # "heading back inside": end the spacewalk now
                w.scenario, w.scenario_until = "auto", 0.0
                self.store.run(
                    "UPDATE events SET m_end=? WHERE astronaut_id=? AND kind='eva' AND m_start<=? AND m_end>?",
                    (self.clock.minute(), row["astronaut_id"], self.clock.minute(), self.clock.minute()),
                )
        else:
            self.store.run("UPDATE alerts SET status='acknowledged' WHERE id=?", (alert_id,))
        return True

    # ================================================================== end of day
    def end_of_day(self, day: int) -> None:
        self.net.add("day", ["worker"], "info", f"End of mission day {day}")
        for a in self.store.astronauts():
            try:
                self.daily_summary(a["id"], day)
            except Exception as exc:  # noqa: BLE001
                self.net.add("error", ["worker"], "failed", f"summary {a['id']}: {exc}")
        self.sync_state["lastDayEnd"] = {"day": day, "at": now_iso()}
        self.sync_all(f"end of day {day}")

    def daily_summary(self, aid: str, day: int | None = None) -> dict[str, Any] | None:
        astronaut = self.store.astronaut(aid)
        if astronaut is None:
            return None
        day = day or M.day_of(self.clock.minute())
        bursts = self.store.bursts_between(
            aid, (day - 1) * M.DAY_MIN, day * M.DAY_MIN
        ) or self.store.recent_bursts(aid, S.BURSTS_PER_MISSION_DAY)
        if not bursts:
            return None
        alerts = (
            self.store.scalar(
                "SELECT COUNT(*) FROM alerts WHERE astronaut_id=? AND code!='INFO' AND "
                "mission_minute>=? AND mission_minute<?",
                (aid, (day - 1) * M.DAY_MIN, day * M.DAY_MIN),
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
            astronaut=aid,
        )
        self._raise_alert(
            aid, rules.Decision(rules.INFO, "summary", f"Your mission day {day} summary is ready.", {})
        )
        return {"id": sid, "missionDay": day, "text": text, "facts": facts, "wordedBy": source, "check": note}

    # ================================================================== agent
    def ask(self, aid: str, question: str) -> dict[str, Any]:
        self.net.add(
            "agent", [aid, "tunnel", "agent"], "info", f"{aid} asks the onboard agent", astronaut=aid
        )
        text, source = ai.answer(question, self.astronaut_view(aid))
        self.store.run(
            "INSERT INTO agent_log (time, astronaut_id, question, answer, source) VALUES (?,?,?,?,?)",
            (now_iso(), aid, question[:500], text[:2000], source),
        )
        self.net.add(
            "agent", ["agent", "tunnel", aid], "ok", f"Agent answered {aid} ({source})", astronaut=aid
        )
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
        return {"id": rid, "event": eid, "activeUntil": until, "summary": summary, "link": link}

    def refresh_space_weather(self) -> None:
        """Pull recent DONKI records (real time) for the hub's space-weather panel. Offline is fine."""
        try:
            for kind in donki.KINDS:
                recs, base = donki.fetch(kind)
                for r in recs:
                    try:
                        eid, etime, summary, link = donki.describe(kind, r)
                    except (KeyError, TypeError):
                        continue
                    self.store.run(
                        "INSERT OR IGNORE INTO space_weather (id, kind, event_time, received_at,"
                        " active_until, summary, link, source, replay) VALUES (?,?,?,?,NULL,?,?,?,0)",
                        (eid, kind, etime, now_iso(), summary, link, "NASA DONKI (live)"),
                    )
            self.donki_state = {"lastFetch": now_iso(), "source": base, "error": None}
            self.net.add("donki", ["donki", "link", "d1"], "ok", f"DONKI pulled ({base})")
        except Exception as exc:  # noqa: BLE001
            self.donki_state = {"lastFetch": now_iso(), "source": None, "error": str(exc)[:200]}
            self.net.add(
                "donki",
                ["d1", "link", "donki"],
                "failed",
                "DONKI unreachable (offline?). Replay still works.",
            )

    # ================================================================== link to Earth
    def blackout(self, m: float | None = None) -> dict[str, Any] | None:
        m = self.clock.minute() if m is None else m
        return self.store.one(
            "SELECT * FROM events WHERE kind='blackout' AND m_start<=? AND m_end>? LIMIT 1", (m, m)
        )

    @property
    def earth_url(self) -> str | None:
        """Where the outbox goes: the Cloudflare Worker when configured, otherwise NASA directly."""
        return self.cf_url or self.nasa_url

    @property
    def via(self) -> str:
        return "cloudflare" if self.cf_url else "direct"

    def _nasa(self, method: str, path: str, body: Any = None, timeout: float = 5.0) -> tuple[int | None, Any]:
        """Talk to Earth. Through the Worker the batch route is /outbox and every request carries the key."""
        base = self.earth_url
        if not base:
            return None, None
        headers = {"Content-Type": "application/json"}
        if self.cf_url:
            path = {"/batch": "/outbox"}.get(path, path)
            headers["x-medvital-key"] = self.cf_key or ""
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
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

    def sync_tick(self) -> None:
        """Every second: urgent alerts go now; everything else waits for the end of the day."""
        if self.store.scalar("SELECT COUNT(*) FROM outbox WHERE urgent=1"):
            self.sync_once(urgent_only=True, reason="urgent alert")
        # after a blackout or a cut link, a missed day-end batch is sent as soon as the link is back
        if self.sync_state.get("pendingDayEnd") and not self.blackout():
            self.sync_all("delayed day-end batch")

    def sync_all(self, reason: str) -> dict[str, Any]:
        total = {"sent": 0, "confirmed": 0}
        for _ in range(200):
            r = self.sync_once(reason=reason)
            total["sent"] += r["sent"]
            total["confirmed"] += r["confirmed"]
            if r["sent"] == 0 or r["confirmed"] == 0:
                break
        delivered = self.store.scalar("SELECT COUNT(*) FROM outbox") == 0
        self.sync_state["pendingDayEnd"] = not delivered
        if total["sent"]:
            self.sync_state["history"] = (
                [{"reason": reason, **total, "at": now_iso(), "mission": M.describe(self.clock.minute())}]
                + self.sync_state["history"]
            )[:20]
            self.net.add(
                "dayend",
                ["outbox", "link", "nasa"],
                "ok" if delivered else "failed",
                f"{reason}: {total['sent']} records sent, NASA confirmed {total['confirmed']}",
                count=total["sent"],
            )
            if total["confirmed"]:
                self.net.add(
                    "ack",
                    ["nasa", "link", "outbox"],
                    "ok",
                    f"NASA confirmed {total['confirmed']} records",
                    count=total["confirmed"],
                )
        return total

    def sync_once(self, urgent_only: bool = False, reason: str = "") -> dict[str, Any]:
        """Send the oldest outbox records to Earth (the Cloudflare Worker or NASA); delete only confirmed ids."""
        rows = self.store.outbox_batch(SYNC_BATCH, urgent_only=urgent_only)
        if not rows:
            return {"linkUp": self.sync_state["linkUp"], "sent": 0, "confirmed": 0}
        if not self.earth_url:
            self.sync_state.update(linkUp=None, lastError="NASA_URL not set", lastAttempt=now_iso())
            return {"linkUp": None, "sent": 0, "confirmed": 0, "problem": "NASA_URL not set"}
        bo = self.blackout()
        if bo:
            self.sync_state.update(linkUp=False, lastError="scheduled blackout", lastAttempt=now_iso())
            return {"linkUp": False, "sent": 0, "confirmed": 0, "problem": "scheduled blackout"}
        records = [json.loads(r["body"]) for r in rows]
        t0 = time.perf_counter()
        status, answer = self._nasa("POST", "/batch", {"records": records}, timeout=15)
        ms = round((time.perf_counter() - t0) * 1000)
        self.sync_state["lastAttempt"] = now_iso()
        if status != 200 or not isinstance(answer, dict) or not isinstance(answer.get("saved"), list):
            who = "Cloudflare" if self.cf_url else "NASA"
            problem = (
                f"link down ({who} answered 503)"
                if status == 503
                else f"{who} unreachable"
                if status is None
                else "Cloudflare refused the key (401)"
                if status == 401 and self.cf_url
                else f"{who} answered HTTP {status}"
            )
            self.sync_state.update(
                linkUp=False,
                lastError=problem,
                pendingDayEnd=not urgent_only or self.sync_state.get("pendingDayEnd", False),
                last={"sent": len(records), "confirmed": 0, "at": now_iso()},
            )
            self.net.add(
                "sync",
                ["outbox", "link", "nasa"],
                "failed",
                f"{len(records)} record(s) not delivered: {problem}. Kept in the outbox.",
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
        if urgent_only:
            self.net.add(
                "sync",
                ["outbox", "link", "nasa"],
                "alert",
                f"Urgent: {len(records)} alert(s) sent to NASA now ({reason})",
                ms=ms,
            )
            self.net.add("ack", ["nasa", "link", "outbox"], "ok", f"NASA confirmed {len(confirmed)}")
        return {"linkUp": True, "sent": len(records), "confirmed": len(confirmed)}

    def link(self, up: bool | None = None) -> dict[str, Any]:
        if up is None:
            status, ans = self._nasa("GET", "/link")
        else:
            status, ans = self._nasa("POST", "/link", {"up": bool(up)})
            self.net.add(
                "link", ["link"], "ok" if up else "failed", f"Link to Earth switched {'UP' if up else 'DOWN'}"
            )
            if up:
                self.sync_state["pendingDayEnd"] = True
        reachable = status == 200 and isinstance(ans, dict)
        bo = self.blackout()
        return {
            "nasaUrl": self.nasa_url,
            "via": self.via,
            "cloudflareUrl": self.cf_url,
            "reachable": reachable,
            "up": (ans.get("up") if reachable else None),
            "blackout": bo["title"] if bo else None,
        }

    # ================================================================== views
    def clock_view(self) -> dict[str, Any]:
        m = self.clock.minute()
        nxt = (M.day_of(m)) * M.DAY_MIN
        return {
            **M.describe(m),
            "daySeconds": S.DAY_SECONDS,
            "secondsToDayEnd": round(self.clock.real_seconds_until(nxt), 1),
            "blackout": (self.blackout(m) or {}).get("title"),
            "sepActive": M.sep_active(m) is not None or self.solar_active() is not None,
        }

    def devices(self) -> list[dict[str, Any]]:
        out = []
        now = datetime.now(UTC)
        self.sim.sync_crew()
        for a in self.store.astronauts():
            last = self.store.recent_bursts(a["id"], 1)
            age = (
                (now - datetime.fromisoformat(last[0]["received_at"].replace("Z", "+00:00"))).total_seconds()
                if last
                else None
            )
            w = self.sim.wearers.get(a["id"])
            out.append(
                {
                    "astronautId": a["id"],
                    "name": a["name"],
                    "role": a["role"],
                    "device": f"WEARABLE-{a['id']}",
                    "connected": age is not None and age < S.OFFLINE_AFTER_S,
                    "worn": bool(w and w.worn),
                    "lastSeenSeconds": round(age, 1) if age is not None else None,
                    "bursts": self.store.burst_count(a["id"]),
                    "state": last[0]["state"] if last else None,
                    "blocked": self.store.scalar(
                        "SELECT COUNT(*) FROM rejected WHERE astronaut_id=?", (a["id"],)
                    )
                    or 0,
                    "alertsDown": self.store.scalar(
                        "SELECT COUNT(*) FROM bursts WHERE astronaut_id=? AND alert IS NOT NULL", (a["id"],)
                    )
                    or 0,
                    "scenario": w.scenario if w else "auto",
                }
            )
        return out

    def events(
        self,
        aid: str | None = None,
        upcoming: bool = True,
        limit: int = 40,
        kinds: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        m = self.clock.minute()
        sql = "SELECT * FROM events WHERE " + ("m_end > ?" if upcoming else "m_start <= ?")
        args: list[Any] = [m]
        if aid:
            sql += " AND (astronaut_id = ? OR astronaut_id IS NULL)"
            args.append(aid)
        if kinds:
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"
            args += list(kinds)
        sql += " ORDER BY m_start " + ("ASC" if upcoming else "DESC") + " LIMIT ?"
        rows = self.store.all(sql, (*args, limit))
        for r in rows:
            r["when"] = M.clock_label(r["m_start"])
            r["inMinutes"] = round(r["m_start"] - m, 1)
            r["realSeconds"] = round(self.clock.real_seconds_until(r["m_start"]), 1)
        return rows

    def measurements(self, aid: str) -> dict[str, Any]:
        """Every value the 3D body shows, with where it came from and a short history."""
        latest = self.store.latest_tests(aid)
        values = {k: r["value"] for k, r in latest.items()}
        sources = {
            k: {"origin": r["origin"], "source": r["source"], "missionMinute": r["mission_minute"]}
            for k, r in latest.items()
        }
        bursts = self.store.recent_bursts(aid, 40)
        a = self.store.astronaut(aid)
        prof = a["profile"]
        valid = [b for b in bursts if b["quality"] == "valid"]
        if valid:
            last = valid[-1]
            live = {"hr.rest": round(last["heart_rate"]), "spo2.pct": round(last["spo2"])}
            if last.get("resp_rate"):
                live["resp.rate"] = round(last["resp_rate"])
            if last.get("skin_temp"):
                live["temp.c"] = round(last["skin_temp"], 1)
            values.update(live)
            for k in live:
                sources[k] = {
                    "origin": "simulated",
                    "source": "wearable (live)",
                    "missionMinute": last["mission_minute"],
                }
        total = bursts[-1]["total_dose"] if bursts else 0.0
        values["radiation.careerMsv"] = round(prof.get("prior_career_msv", 0) + total, 2)
        sources["radiation.careerMsv"] = {
            "origin": "measured",
            "source": "Curiosity RAD dose rate x mission time "
            f"(+ {prof.get('prior_career_msv', 0)} mSv before this mission)",
        }
        values["sex"] = prof.get("sex", "f")
        hist = {
            "hr": [round(b["heart_rate"]) if b["quality"] == "valid" else None for b in bursts],
            "spo2": [round(b["spo2"]) if b["quality"] == "valid" else None for b in bursts],
            "resp": [round(b["resp_rate"]) if b.get("resp_rate") else None for b in bursts],
            "temp": [round(b["skin_temp"], 1) if b.get("skin_temp") else None for b in bursts],
            "rad": [round(prof.get("prior_career_msv", 0) + b["total_dose"], 3) for b in bursts],
        }
        for vid, key in (
            ("bp", "bp.sys"),
            ("glucose", "glucose.mgdl"),
            ("rt", "pvt.meanRtMs"),
            ("sleep", "sleep.hours"),
            ("pain", "back.pain"),
            ("hgb", "hemoglobin.gdl"),
            ("urine", "urine.volumeL"),
            ("mass", "mass.changePct"),
            ("hip", "bmd.hipPct"),
            ("str", "strength.changePct"),
            ("vitd", "vitd.ngml"),
        ):
            hist[vid] = [r["value"] for r in self.store.test_history(aid, key, 14)]
        return {
            "values": values,
            "sources": sources,
            "history": hist,
            "doseRate": bursts[-1]["dose_rate"] if bursts else None,
            "radRef": bursts[-1]["rad_ref"] if bursts else None,
            "state": bursts[-1]["state"] if bursts else None,
        }

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
        m = self.clock.minute()
        sep = M.sep_active(m)
        active = self.store.one(
            "SELECT * FROM alerts WHERE astronaut_id=? ORDER BY time DESC LIMIT 1", (aid,)
        )
        last_summary = self.store.one(
            "SELECT * FROM summaries WHERE astronaut_id=? ORDER BY time DESC LIMIT 1", (aid,)
        )
        if last_summary:
            last_summary["facts"] = json.loads(last_summary["facts"])
        day = M.day_of(m)
        today_bursts = self.store.bursts_between(aid, (day - 1) * M.DAY_MIN, day * M.DAY_MIN)
        today = rules.day_facts(today_bursts, prof, 0) if today_bursts else None
        event_dose = 0.0
        if sep or wx:
            start_m = sep[0] if sep else None
            during = [
                b
                for b in bursts
                if (start_m is not None and (b["mission_minute"] or 0) >= start_m)
                or (wx and b["received_at"] >= wx["received_at"])
            ]
            if during:
                event_dose = max(0.0, during[-1]["total_dose"] - during[0]["total_dose"])
        career = prof.get("prior_career_msv", 0) + total
        return {
            "id": aid,
            "name": a["name"],
            "role": a["role"],
            "profile": prof,
            "report": a["report"],
            "latest": latest,
            "bursts": bursts,
            "burstCount": self.store.burst_count(aid),
            "clock": self.clock_view(),
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
                "radRef": latest["rad_ref"] if latest else None,
            },
            "spaceWeather": {
                "active": wx
                or (
                    {"summary": f"{sep[2]} (real DONKI event on the mission calendar)", "link": sep[3]}
                    if sep
                    else None
                ),
                "upcoming": self.events(None, kinds=("space_weather",), limit=6),
            },
            "activeAlert": active,
            "lastSummary": last_summary,
            "today": today,
            "upcoming": self.events(aid, limit=12),
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

    def _observation_count(self, aid: str) -> int:
        if self.obs_path:
            with sqlite3.connect(self.obs_path) as db:
                return db.execute("SELECT COUNT(*) FROM observations WHERE subject_id=?", (aid,)).fetchone()[
                    0
                ]
        return len(self.obs.query(subject_id=aid, limit=1_000_000))

    def verify(self) -> dict[str, Any]:
        """Double-check every hop: what the wearables sent, what the hub kept, what NASA has."""
        nasa = self.nasa_stats()
        rows = []
        for a in self.store.astronauts():
            aid = a["id"]
            bursts = self.store.burst_count(aid)
            max_seq = self.store.scalar("SELECT MAX(seq) FROM bursts WHERE astronaut_id=?", (aid,)) or 0
            first_seq = self.store.scalar("SELECT MIN(seq) FROM bursts WHERE astronaut_id=?", (aid,)) or 1
            flagged = (
                self.store.scalar(
                    "SELECT COUNT(*) FROM bursts WHERE astronaut_id=? AND quality!='valid'", (aid,)
                )
                or 0
            )
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
                    "name": a["name"],
                    "wearableSent": max(0, max_seq - first_seq + 1) if bursts else 0,
                    "hubBursts": bursts,
                    "missingBursts": max(0, (max_seq - first_seq + 1) - bursts) if bursts else 0,
                    "flagged": flagged,
                    "observations": self._observation_count(aid),
                    "recordsCreated": created,
                    "byType": by_type,
                    "outboxPending": pending,
                    "confirmedByNasa": synced,
                    "atNasa": at_nasa,
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
