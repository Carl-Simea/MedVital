"""Mission clock, real NASA data on the mission timeline, and the mission schedule (upcoming events).

* Clock: mission minutes since day 1 00:00. One real ``DAY_SECONDS`` = one mission day.
* RAD: the dose rate the crew sees is a real Curiosity RAD observation (cruise days -> cruise files,
  surface days -> surface sols), converted to dose equivalent with RAD's measured mean quality factor.
* DONKI: the 60-day window of real space weather is replayed on the mission calendar
  (mission day 1 00:00 = DONKI_EPOCH). Flares, CMEs, SEPs, storms and WSA-ENLIL arrival forecasts at Mars.
* Schedule: sleep, exercise, onboard tests, spacewalks, landing, link blackouts, plus real space weather.
"""

from __future__ import annotations

import bisect
import csv
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

from medvital.hub import settings as S

DAY_MIN = 1440.0
START_MINUTE = 7 * 60.0  # the mission opens on day 1 at 07:00 (wake-up)


# ============================================================================ clock
class MissionClock:
    """Mission minutes since day 1 00:00. ``start_real`` is persisted so a restart continues the mission."""

    def __init__(self, start_real: float | None = None, day_seconds: float = S.DAY_SECONDS) -> None:
        self.start_real = start_real if start_real is not None else time.time()
        self.day_seconds = day_seconds

    def minute(self, at: float | None = None) -> float:
        return START_MINUTE + ((at or time.time()) - self.start_real) / self.day_seconds * DAY_MIN

    def real_seconds_until(self, minute: float) -> float:
        return (minute - self.minute()) / DAY_MIN * self.day_seconds


def day_of(m: float) -> int:
    return int(m // DAY_MIN) + 1


def hour_of(m: float) -> float:
    return (m % DAY_MIN) / 60.0


def clock_text(m: float) -> str:
    h = hour_of(m)
    return f"{int(h):02d}:{int((h % 1) * 60):02d}"


LANDING_MIN = (S.LANDING_DAY - 1) * DAY_MIN + S.LANDING_HOUR * 60


def phase_of(m: float) -> str:
    return "cruise" if m < LANDING_MIN else "surface"


def describe(m: float) -> dict[str, Any]:
    p = phase_of(m)
    return {
        "minute": round(m, 2),
        "day": day_of(m),
        "time": clock_text(m),
        "hour": round(hour_of(m), 3),
        "phase": p,
        "phaseLabel": "Cruise to Mars" if p == "cruise" else "Mars surface",
        "dayFraction": round((m % DAY_MIN) / DAY_MIN, 4),
    }


EPOCH = datetime.fromisoformat(S.DONKI_EPOCH)


def to_minute(utc: str) -> float | None:
    """Real UTC time (DONKI) -> mission minute."""
    try:
        t = datetime.fromisoformat(utc.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return (t - EPOCH).total_seconds() / 60.0


def to_real(m: float) -> datetime:
    return EPOCH + timedelta(minutes=m)


# ============================================================================ Curiosity RAD
@dataclass(frozen=True)
class RadPoint:
    ugy_h: float  # absorbed dose rate, tissue-equivalent detector E
    usv_h: float  # dose-equivalent rate = ugy_h x RAD mean quality factor
    phase: str
    source: str  # file + observation, or "published mean"


@lru_cache(maxsize=1)
def _rad() -> dict[str, list[list[tuple[float, float, str]]]]:
    """phase -> list of days; each day = sorted [(hour of day, uGy/h, ref)]."""
    out: dict[str, dict[int, list[tuple[float, float, str]]]] = {"cruise": {}, "surface": {}}
    if not S.RAD_FILE.exists():
        return {"cruise": [], "surface": []}
    with open(S.RAD_FILE, newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                dose = float(r["dose_e_ugy_h"])
            except (KeyError, ValueError):
                continue
            if dose <= 0:
                continue
            m = re.search(r"(\d\d):(\d\d):(\d\d)", r.get("START_OBS_MARS") or "")
            if m is None:
                m = re.search(r"(\d\d):(\d\d):(\d\d)", r.get("START_OBS_UTC") or "")
            hour = int(m.group(1)) + int(m.group(2)) / 60 if m else 0.0
            ref = f"RAD {r['file']} obs {r['obs']}"
            out[r["phase"]].setdefault(int(r["file_index"]), []).append((hour, dose, ref))
    return {p: [sorted(v) for _, v in sorted(days.items())] for p, days in out.items()}


def rad_at(m: float) -> RadPoint:
    p = phase_of(m)
    days = _rad()[p]
    q = S.QUALITY_FACTOR[p]
    if not days:
        ugy = S.RAD_FALLBACK_UGY_H[p]
        return RadPoint(ugy, ugy * q, p, "published mean (rad_dose.csv missing)")
    d = day_of(m) - 1 if p == "cruise" else day_of(m) - S.LANDING_DAY
    obs = days[d % len(days)]
    hours = [o[0] for o in obs]
    i = min(len(obs) - 1, bisect.bisect_left(hours, hour_of(m)))
    _, ugy, ref = obs[i]
    return RadPoint(ugy, ugy * q, p, ref)


def rad_summary() -> dict[str, Any]:
    days = _rad()
    return {
        p: {"days": len(v), "observations": sum(len(d) for d in v), "qualityFactor": S.QUALITY_FACTOR[p]}
        for p, v in days.items()
    }


# ============================================================================ DONKI
@lru_cache(maxsize=1)
def donki() -> dict[str, Any]:
    if not S.DONKI_FILE.exists():
        return {"events": {}}
    return json.loads(S.DONKI_FILE.read_text())


def space_weather_events() -> list[dict[str, Any]]:
    """Real DONKI records placed on the mission calendar."""
    ev = donki().get("events", {})
    out: list[dict[str, Any]] = []

    def add(m, kind, title, detail, rid, link, end=None):
        if m is not None and m >= 0:
            out.append(
                {
                    "m_start": m,
                    "m_end": end if end is not None else m,
                    "kind": "space_weather",
                    "astronaut_id": None,
                    "title": title,
                    "detail": detail,
                    "source": f"NASA DONKI {rid}",
                    "link": link,
                    "sw_type": kind,
                }
            )

    for f in ev.get("FLR", []):
        cls = f.get("classType") or ""
        try:
            big = cls[:1] == "X" or (cls[:1] == "M" and float(cls[1:]) >= 5)
        except ValueError:
            big = False
        if big:  # X-class and strong M-class flares only (the window has 200+ weaker ones)
            end = to_minute(f.get("endTime") or "")  # NASA reports begin and end for flares
            add(
                to_minute(f.get("beginTime") or f.get("peakTime") or ""),
                "FLR",
                f"Class {cls} solar flare",
                f"Active region {f.get('activeRegionNum') or 'n/a'}, {f.get('sourceLocation') or ''}".strip(
                    ", "
                ),
                f.get("flrID"),
                f.get("link"),
                end=end,
            )
    for c in ev.get("CME", []):
        speed = max([a.get("speed") or 0 for a in c.get("cmeAnalyses") or []] or [0])
        if speed >= 800:
            add(
                to_minute(c.get("startTime") or ""),
                "CME",
                f"Coronal mass ejection, {speed:.0f} km/s",
                (c.get("note") or "")[:200],
                c.get("activityID"),
                c.get("link"),
            )
    for s in ev.get("SEP", []):
        inst = ", ".join(i.get("displayName", "") for i in s.get("instruments") or [])
        m = to_minute(s.get("eventTime") or "")
        add(
            m,
            "SEP",
            "Solar energetic particle event",
            f"Detected by {inst}. Raises radiation; storm shelter.",
            s.get("sepID"),
            s.get("link"),
            end=(m + S.SEP_ACTIVE_HOURS * 60) if m is not None else None,
        )
    for g in ev.get("GST", []):
        kp = max([k.get("kpIndex") or 0 for k in g.get("allKpIndex") or []] or [0])
        add(
            to_minute(g.get("startTime") or ""),
            "GST",
            f"Geomagnetic storm at Earth (Kp {kp:g})",
            "Can disturb the link to Earth.",
            g.get("gstID"),
            g.get("link"),
        )
    for w in ev.get("WSAEnlilSimulations", []):
        for imp in w.get("impactList") or []:
            if imp.get("location") == "Mars":
                issued = to_minute(w.get("modelCompletionTime") or "")
                add(
                    to_minute(imp.get("arrivalTime") or ""),
                    "ENLIL",
                    "Forecast: CME arrives at Mars",
                    f"WSA-ENLIL forecast issued mission {clock_label(issued)}"
                    + (" (glancing blow)" if imp.get("isGlancingBlow") else ""),
                    w.get("simulationID"),
                    w.get("link"),
                )
    return sorted(out, key=lambda e: e["m_start"])


def clock_label(m: float | None) -> str:
    return f"day {day_of(m)} {clock_text(m)}" if m is not None else "?"


def utc_label(m: float | None) -> str:
    """The real date of a mission minute: mission minute 0 is DONKI_EPOCH (the replayed 2024 window)."""
    if m is None:
        return "?"
    return (EPOCH + timedelta(minutes=m)).strftime("%Y-%m-%d %H:%M UTC")


@lru_cache(maxsize=1)
def sep_windows() -> list[tuple[float, float, str, str]]:
    """SEP activity windows. Several DONKI SEP records describe one event seen by different instruments,
    so overlapping windows are merged."""
    merged: list[list] = []
    for e in space_weather_events():
        if e["sw_type"] != "SEP":
            continue
        if merged and e["m_start"] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e["m_end"])
        else:
            merged.append([e["m_start"], e["m_end"], e["source"], e["link"] or ""])
    return [tuple(w) for w in merged]


def sep_active(m: float) -> tuple[float, float, str, str] | None:
    return next((w for w in sep_windows() if w[0] <= m < w[1]), None)


# ============================================================================ schedule
def plan_for(astronaut_id: str, exercise_hour: float, from_day: int = 1) -> list[dict[str, Any]]:
    """The mission plan for one astronaut (simulated plan, not real crew timelines)."""
    rows: list[dict[str, Any]] = []
    src = "mission plan (simulated)"

    def add(day, hour, hours, kind, title, detail=""):
        start = (day - 1) * DAY_MIN + hour * 60
        rows.append(
            {
                "m_start": start,
                "m_end": start + hours * 60,
                "kind": kind,
                "astronaut_id": astronaut_id,
                "title": title,
                "detail": detail,
                "source": src,
                "link": None,
            }
        )

    for d in range(from_day, S.MISSION_DAYS + 1):
        add(d, S.SLEEP_START_H, 24 - S.SLEEP_START_H + S.SLEEP_END_H, "sleep", "Sleep period")
        add(
            d, 7.5, 0.25, "test", "Morning check", "Blood pressure, body mass, reaction test (PVT), back pain"
        )
        add(
            d,
            exercise_hour,
            S.EXERCISE_TARGET_MIN / 60,
            "exercise",
            "Exercise: resistance + treadmill",
            "Counters bone and muscle loss",
        )
        if d % 3 == sum(map(ord, astronaut_id)) % 3:
            add(d, 8.0, 0.25, "test", "Blood draw", "Hemoglobin, vitamin D, glucose")
            add(
                d, 7.0, 24, "test", "24-hour urine collection", "Urine volume and urinary calcium (bone loss)"
            )
        if d % 4 == 1:
            add(d, 15.0, 0.75, "test", "Fitness test", "Strength and aerobic capacity vs. pre-flight")
        pair = S.EVA_PLAN.get(d)
        if pair and astronaut_id in pair:
            add(
                d,
                S.EVA_START_H,
                S.EVA_END_H - S.EVA_START_H,
                "eva",
                "Spacewalk (EVA)",
                f"With {[a for a in pair if a != astronaut_id][0]}",
            )
    return rows


def crew_plan() -> list[dict[str, Any]]:
    rows = [
        {
            "m_start": LANDING_MIN,
            "m_end": LANDING_MIN + 60,
            "kind": "landing",
            "astronaut_id": None,
            "title": "Mars landing",
            "detail": "End of cruise; surface operations begin",
            "source": "mission plan (simulated)",
            "link": None,
        }
    ]
    for d in range(S.LANDING_DAY, S.MISSION_DAYS + 1):
        start = (d - 1) * DAY_MIN + S.BLACKOUT_START_H * 60
        rows.append(
            {
                "m_start": start,
                "m_end": start + (S.BLACKOUT_END_H - S.BLACKOUT_START_H) * 60,
                "kind": "blackout",
                "astronaut_id": None,
                "title": "Link to Earth blackout",
                "detail": "Earth below the horizon; records wait in the outbox",
                "source": "mission plan (simulated)",
                "link": None,
            }
        )
    cruise_gap = 5 * DAY_MIN - DAY_MIN + 13 * 60
    rows.append(
        {
            "m_start": cruise_gap,
            "m_end": cruise_gap + 5 * 60,
            "kind": "blackout",
            "astronaut_id": None,
            "title": "Link to Earth blackout",
            "detail": "Deep Space Network antenna handover gap",
            "source": "mission plan (simulated)",
            "link": None,
        }
    )
    return rows + space_weather_events()
