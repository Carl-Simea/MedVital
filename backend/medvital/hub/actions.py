"""What an astronaut does with their own buttons: sleep, leave the spacecraft, mood check-in; plus skip ahead.

Mixed into ``Hub`` (service.py). Timings for the spacewalk warning are demo values in real seconds
(settings.EVA_WARN_AFTER_S, EVA_RETURN_AFTER_WARN_S). The event announced during a spacewalk is the next
real DONKI event on the mission calendar when one is close; otherwise a simulated "window closes".
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from medvital.hub import mission as M
from medvital.hub import rules
from medvital.hub import settings as S

if TYPE_CHECKING:
    from medvital.hub.service import Hub


class ActionError(Exception):
    """The action cannot happen now (shown to the astronaut as is)."""


def _hm(minutes: float) -> str:
    h, mm = divmod(int(round(minutes)), 60)
    return f"{h} h {mm:02d} min" if h else f"{mm} min"


class CrewActions:
    evas: dict[str, dict[str, Any]]

    # ------------------------------------------------------------------ sleep
    def set_sleep(self: Hub, aid: str, asleep: bool) -> dict[str, Any]:
        self.sim.sync_crew()
        w = self.sim.wearers[aid]
        m = self.clock.minute()
        if asleep:
            if w.manual == "spacewalk":
                raise ActionError("Go back inside before you sleep.")
            if w.manual != "asleep":
                w.manual, w.manual_since = "asleep", m
                self.net.add("state", [aid, "hub"], "info", f"{aid} went to sleep", astronaut=aid)
            return {"asleep": True, "since": M.clock_label(w.manual_since)}
        if w.manual != "asleep":
            return {"asleep": False}
        hours = max(0.0, (m - w.manual_since) / 60)
        w.manual = None
        target = w.profile.get("sleep_target_h", 7.0)
        self.add_measurements(
            aid,
            m,
            {"sleep.hours": round(hours, 1), "sleep.quality": max(1, min(5, round(4 - max(0, target - hours))))},
            "simulated",
            "wearable sleep log (Sleep button)",
        )
        self.net.add("state", [aid, "hub"], "info", f"{aid} woke up after {hours:.1f} h", astronaut=aid)
        self.check_sleep_mood(aid)
        return {"asleep": False, "hours": round(hours, 1)}

    def sleeping_hours(self: Hub, aid: str) -> float | None:
        w = self.sim.wearers.get(aid)
        if w is None or w.manual != "asleep":
            return None
        return round(max(0.0, (self.clock.minute() - w.manual_since) / 60), 1)

    # ------------------------------------------------------------------ mood
    def add_mood(self: Hub, aid: str, score: int) -> dict[str, Any]:
        if not 1 <= score <= 5:
            raise ActionError("Mood is 1 to 5.")
        out = self.add_measurements(aid, self.clock.minute(), {"mood.score": score}, "entered", "mood check-in")
        self.check_sleep_mood(aid)
        return out

    def check_sleep_mood(self: Hub, aid: str) -> None:
        a = self.store.astronaut(aid)
        if a is None:
            return
        prof = a["profile"]
        usual = prof.get("baseline", {}).get("sleep.hours", prof.get("sleep_target_h", 7.0))
        sleep = [r["value"] for r in self.store.test_history(aid, "sleep.hours", 3)]
        mood = self.store.latest_tests(aid).get("mood.score")
        d = rules.sleep_mood(sleep, usual, mood["value"] if mood else None)
        if d is None:
            return
        m = self.clock.minute()
        if self.store.one(  # one check-in request per mission day is enough
            "SELECT 1 FROM alerts WHERE astronaut_id=? AND code=? AND mission_minute>?",
            (aid, rules.CHECK_IN, m - M.DAY_MIN),
        ):
            return
        self._raise_alert(aid, d, m)

    # ------------------------------------------------------------------ leave the spacecraft
    def start_eva(self: Hub, aid: str) -> dict[str, Any]:
        self.sim.sync_crew()
        w = self.sim.wearers[aid]
        if aid in self.evas:
            return self.eva_status(aid) or {}
        if w.manual == "asleep":
            raise ActionError("Wake up before you leave the spacecraft.")
        m = self.clock.minute()
        w.manual, w.manual_since = "spacewalk", m
        self.store.run(
            "INSERT INTO events (m_start, m_end, kind, astronaut_id, title, detail, source, status)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (m, m + 8 * 60, "eva", aid, "Spacewalk (outside now)", "Left the spacecraft", "astronaut", "active"),
        )
        self.evas[aid] = {
            "start_real": time.monotonic(),
            "start_m": m,
            "start_dose": w.total_dose,
            "solar_min": 0.0,
            "event_id": self.store.scalar("SELECT MAX(id) FROM events"),
            "warned": None,
            "forced": False,
        }
        self.net.add("eva", [aid, "hub"], "info", f"{aid} left the spacecraft", astronaut=aid)
        return self.eva_status(aid) or {}

    def eva_tick(self: Hub) -> None:
        """Every second: count time in solar events, warn after 20 s, force the return 15 s later."""
        if not self.evas:
            return
        m = self.clock.minute()
        solar = M.sep_active(m) is not None or self.solar_active() is not None
        for aid, e in list(self.evas.items()):
            if solar:
                e["solar_min"] += S.MISSION_MINUTES_PER_BURST
            elapsed = time.monotonic() - e["start_real"]
            return_now = self.store.one(
                "SELECT 1 FROM alerts WHERE astronaut_id=? AND code=? AND status='active'", (aid, rules.RETURN_NOW)
            )
            if return_now:  # already called back inside (e.g. a solar event): no softer warning on top
                e["forced"] = True
                continue
            if e["warned"] is None and elapsed >= S.EVA_WARN_AFTER_S:
                ev = self.store.one(
                    "SELECT * FROM events WHERE kind='space_weather' AND m_end>=? AND m_start<=? "
                    "ORDER BY m_start LIMIT 1",
                    (m, m + S.EVA_LOOKAHEAD_MIN),
                )
                window = S.EVA_RETURN_AFTER_WARN_S  # real seconds to get back inside
                if ev:
                    # be inside before the event starts (at least a few seconds to react, at most the usual window)
                    window = max(5.0, min(window, self.clock.real_seconds_until(ev["m_start"]) - 1.0))
                    title = ev["title"] if ev["m_start"] > m else f"{ev['title']} (in progress)"
                    when = M.clock_label(ev["m_start"])
                    source, link = ev["source"], ev["link"]
                deadline_m = m + window / self.clock.day_seconds * M.DAY_MIN
                if not ev:
                    title, when = "Spacewalk window closes", M.clock_label(deadline_m)
                    source, link = "mission plan (simulated)", None
                e["warned"] = {
                    "real": time.monotonic(),
                    "window": window,
                    "deadline_m": deadline_m,
                    "title": title,
                    "when": when,
                    "source": source,
                    "link": link,
                }
                self._raise_alert(
                    aid,
                    rules.Decision(
                        rules.GO_INSIDE,
                        "eva_window",
                        f"{'Upcoming' if not ev or ev['m_start'] > m else 'Now'}: {title}, "
                        f"{'at' if not ev or ev['m_start'] > m else 'since'} {when}. "
                        f"Go back inside by {M.clock_label(deadline_m)}.",
                        {"event": title, "eventTime": when, "source": source, "deadline": M.clock_label(deadline_m)},
                    ),
                    m,
                )
            elif (
                e["warned"] is not None
                and not e["forced"]
                and time.monotonic() - e["warned"]["real"] >= e["warned"]["window"]
            ):
                e["forced"] = True
                self._raise_alert(
                    aid,
                    rules.Decision(
                        rules.RETURN_NOW,
                        "eva_deadline",
                        f"Go back inside now. You were due inside by {M.clock_label(e['warned']['deadline_m'])}: "
                        f"{e['warned']['title']}.",
                        {"event": e["warned"]["title"], "source": e["warned"]["source"]},
                    ),
                    m,
                )

    def end_eva(self: Hub, aid: str, forced: bool = False) -> dict[str, Any] | None:
        e = self.evas.pop(aid, None)
        w = self.sim.wearers.get(aid)
        if w is not None and w.manual == "spacewalk":
            w.manual = None
        if e is None:
            return None
        m = self.clock.minute()
        minutes = max(0.0, m - e["start_m"])
        dose = max(0.0, (w.total_dose if w else e["start_dose"]) - e["start_dose"])
        solar = min(e["solar_min"], minutes)
        detail = f"Outside {_hm(minutes)}, received {dose:.3f} mSv"
        if solar:
            detail += f", {_hm(solar)} of it during a solar event"
        if forced:
            detail += " (called back inside)"
        self.store.run(
            "UPDATE events SET m_end=?, title=?, detail=?, status='done' WHERE id=?",
            (m, f"Spacewalk: {_hm(minutes)} outside", detail, e["event_id"]),
        )
        self.add_measurements(
            aid, m, {"eva.minutes": round(minutes), "eva.solarMinutes": round(solar)}, "simulated", "spacewalk log"
        )
        self.add_measurements(
            aid, m, {"eva.doseMsv": round(dose, 4)}, "modeled", "spacewalk dose (Curiosity RAD x demo factors)"
        )
        self.net.add("eva", [aid, "hub"], "alert" if forced else "ok", f"{aid} back inside. {detail}", astronaut=aid)
        return {"minutes": round(minutes), "doseMsv": round(dose, 4), "solarMinutes": round(solar), "detail": detail}

    def eva_status(self: Hub, aid: str) -> dict[str, Any] | None:
        e = self.evas.get(aid)
        if e is None:
            return None
        w = self.sim.wearers.get(aid)
        m = self.clock.minute()
        warned = e["warned"]
        return {
            "outside": True,
            "since": M.clock_label(e["start_m"]),
            "minutes": round(m - e["start_m"]),
            "doseMsv": round(max(0.0, (w.total_dose if w else 0) - e["start_dose"]), 4),
            "solarMinutes": round(e["solar_min"]),
            "warning": None
            if warned is None
            else {
                "event": warned["title"],
                "when": warned["when"],
                "source": warned["source"],
                "link": warned["link"],
                "deadline": M.clock_label(warned["deadline_m"]),
                "secondsLeft": max(0.0, round(warned["window"] - (time.monotonic() - warned["real"]), 1)),
            },
            "forced": e["forced"],
        }

    # ------------------------------------------------------------------ skip ahead (demo drawer)
    def skip_ahead(self: Hub, to: str = "solar", day: int | None = None) -> dict[str, Any]:
        if self.evas:
            raise ActionError("Someone is outside. Bring them back inside before skipping ahead.")
        m = self.clock.minute()
        if to == "day":
            if not day or day < 1:
                raise ActionError("Pick a mission day.")
            target = (day - 1) * M.DAY_MIN + 7 * 60
            what = f"day {day} 07:00"
        else:
            nxt = next((w for w in M.sep_windows() if w[0] - 120 > m), None)
            if nxt is None:
                raise ActionError("No more solar events on the mission calendar.")
            target = nxt[0] - 120
            what = f"2 h before the solar particle event of {M.clock_label(nxt[0])}"
        if target <= m:
            raise ActionError("That moment has already passed.")
        shift = (target - m) / M.DAY_MIN * self.clock.day_seconds
        with self._lock:
            self.clock.start_real -= shift
            self.store.meta("mission_start_real", repr(self.clock.start_real))
            self.store.meta("last_tick_minute", repr(target))
            for w in self.sim.wearers.values():
                w.last_m = target  # no backfill of the skipped time
                if w.manual == "asleep":
                    w.manual_since = target
        self.net.add("day", ["hub"], "info", f"Skipped ahead to {M.clock_label(target)} ({what})")
        return {"now": M.clock_label(target), "what": what}
