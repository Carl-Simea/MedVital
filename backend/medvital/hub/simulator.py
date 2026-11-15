"""Simulated crew: every astronaut's wearable and their scheduled onboard tests, driven by the mission plan.

What is real and what is simulated (shown in every record's ``origin`` / ``source``):

* radiation dose rate: a real Curiosity RAD observation for this point of the mission (mission.rad_at),
  times a demo shielding factor, times a demo SEP factor while a real DONKI SEP is active;
* heart rate, SpO2, breathing, skin temperature: SIMULATED around the astronaut's own pre-flight values;
* onboard test results (blood pressure, blood, urine, reaction test, fitness...): SIMULATED around the
  pre-flight values with small drifts;
* bone density: MODELED from the loss rates the 3D body dashboard cites (Sibonga et al. 2015);
  a wearable cannot measure it and nobody scans bone in flight.

Magnitudes are demo signals, not science (CLAUDE.md rule 8).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from medvital.hub import mission as M
from medvital.hub import settings as S

if TYPE_CHECKING:
    from medvital.hub.service import Hub

STATE_HR = {"asleep": (-7, 2.0), "awake": (8, 3.0), "exercise": (65, 6.0), "spacewalk": (30, 5.0)}
STATE_RESP = {"asleep": -1.5, "awake": 0.0, "exercise": 10.0, "spacewalk": 5.0}
# Monthly bone-density loss rates (%/month) as cited in body-dashboard/public/parts.mjs (src boneSibonga15).
BONE_RATE_PCT_MONTH = {"bmd.hipPct": 1.5, "bmd.lumbarPct": 1.0, "bmd.wholeBodyPct": 0.3}
SIM = "simulated"


@dataclass
class Wearer:
    astronaut_id: str
    profile: dict[str, Any]
    rng: random.Random
    worn: bool = True
    scenario: str = "auto"
    scenario_until: float = 0.0
    glitch_next: bool = False
    seq: int = 0
    total_dose: float = 0.0  # mSv since launch
    last_m: float | None = None
    exercise_log: dict[int, float] = field(default_factory=dict)  # mission day -> minutes
    replay_until: float = 0.0  # demo solar-event replay (mission minute)
    manual: str | None = None  # "asleep" or "spacewalk": set by the astronaut's own buttons, until released
    manual_since: float = 0.0  # mission minute the manual state began


class CrewSimulator:
    def __init__(self, hub: Hub, seed: int = 7) -> None:
        self.hub = hub
        self.seed = seed
        self.wearers: dict[str, Wearer] = {}

    # ------------------------------------------------------------------ crew
    def sync_crew(self) -> None:
        for a in self.hub.store.astronauts():
            if a["id"] not in self.wearers:
                last = self.hub.store.recent_bursts(a["id"], 1)
                w = Wearer(a["id"], a["profile"], random.Random(f"{self.seed}-{a['id']}"))
                if last:
                    w.seq, w.total_dose, w.last_m = (
                        last[0]["seq"] or 0,
                        last[0]["total_dose"] or 0.0,
                        last[0]["mission_minute"],
                    )
                self.wearers[a["id"]] = w

    def set_scenario(self, aid: str, scenario: str, now_m: float) -> None:
        w = self.wearers[aid]
        w.scenario = scenario
        w.scenario_until = now_m + {"spacewalk": 240, "exercise": 90, "sleep": 480, "hr_spike": 300}.get(
            scenario, 0
        )

    # ------------------------------------------------------------------ one tick (one burst per astronaut)
    def tick(self, m: float) -> None:
        self.sync_crew()
        for w in self.wearers.values():
            prev = w.last_m if w.last_m is not None else m - S.MISSION_MINUTES_PER_BURST
            if w.worn:
                self.hub.handle_burst(self.burst(w, m), simulated=True)
            self.scheduled_tests(w, prev, m)
            w.last_m = m

    def state(self, w: Wearer, m: float) -> str:
        if w.manual:  # the astronaut's own Sleep / Leave the spacecraft button wins over the plan
            return w.manual
        if w.scenario != "auto":
            if m < w.scenario_until:
                forced = S.SCENARIOS[w.scenario].get("state")
                if forced:
                    return forced
            else:
                w.scenario = "auto"
        ev = self.hub.store.one(
            "SELECT kind FROM events WHERE astronaut_id=? AND kind IN ('eva','exercise','sleep') AND m_start<=? "
            "AND m_end>? ORDER BY CASE kind WHEN 'eva' THEN 0 WHEN 'exercise' THEN 1 ELSE 2 END LIMIT 1",
            (w.astronaut_id, m, m),
        )
        return (
            {"eva": "spacewalk", "exercise": "exercise", "sleep": "asleep"}.get(ev["kind"], "awake")
            if ev
            else "awake"
        )

    def burst(self, w: Wearer, m: float) -> dict[str, Any]:
        p, b, r = w.profile, w.profile.get("baseline", {}), w.rng
        state = self.state(w, m)
        h = M.hour_of(m)
        off, sd = STATE_HR[state]
        hr = p["resting_hr"] + off + 3 * math.sin(2 * math.pi * (h - 16) / 24) + r.gauss(0, sd)
        spo2 = p["spo2"] + r.gauss(0, 0.5) - (0.5 if state == "exercise" else 0)
        spike = S.SCENARIOS["hr_spike"] if (w.scenario == "hr_spike" and m < w.scenario_until) else None
        if spike:
            hr, spo2 = p["resting_hr"] + 8 + spike["hrOffset"] + r.gauss(0, 3), spo2 + spike["spo2Offset"]
        if w.glitch_next:
            hr, w.glitch_next = 240.0, False  # a physically impossible sensor reading
        resp = b.get("resp.rate", 14) + STATE_RESP[state] + r.gauss(0, 0.6)
        temp = (
            b.get("temp.c", 36.6)
            + 0.25 * math.sin(2 * math.pi * (h - 17) / 24)
            + (0.4 if state == "exercise" else 0)
            + r.gauss(0, 0.05)
        )
        rad = M.rad_at(m)
        outside = state == "spacewalk"
        shield = 1.0 if (rad.phase == "cruise" or outside) else S.HABITAT_SHIELDING
        dose = rad.usv_h * shield
        if M.sep_active(m) or m < w.replay_until or self.hub.solar_active() is not None:
            dose *= S.SEP_DOSE_FACTOR * (1.0 if outside else S.SEP_SHIELDED_FRACTION)
        w.total_dose += dose * S.MISSION_MINUTES_PER_BURST / 60 / 1000
        w.seq += 1
        if state == "exercise":
            d = M.day_of(m)
            w.exercise_log[d] = w.exercise_log.get(d, 0) + S.MISSION_MINUTES_PER_BURST
        return {
            "astronautId": w.astronaut_id,
            "deviceKey": self.hub.store.astronaut(w.astronaut_id)["device_key"],
            "seq": w.seq,
            "time": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "missionMinute": round(m, 2),
            "heartRate": round(hr),
            "spo2": round(min(100.0, spo2), 1),
            "state": state,
            "doseRate": round(dose, 2),
            "totalDose": round(w.total_dose, 5),
            "respRate": round(resp, 1),
            "skinTemp": round(temp, 2),
            "radRef": rad.source,
            "scenario": w.scenario,
        }

    # ------------------------------------------------------------------ onboard tests on the schedule
    def scheduled_tests(self, w: Wearer, m0: float, m1: float) -> None:
        aid = w.astronaut_id
        # tests that start in (m0, m1]; the 24-hour urine reports when it ends
        for ev in self.hub.store.all(
            "SELECT * FROM events WHERE astronaut_id=? AND kind IN ('test','sleep','exercise') AND "
            "((m_start>? AND m_start<=?) OR (m_end>? AND m_end<=?))",
            (aid, m0, m1, m0, m1),
        ):
            started, ending = m0 < ev["m_start"] <= m1, m0 < ev["m_end"] <= m1
            if ev["kind"] == "sleep" and ending:
                self.record(w, m1, self.sleep_values(w, ev), SIM, "wearable sleep log")
            elif ev["kind"] == "exercise" and ending:
                self.record(w, m1, self.exercise_values(w, m1), SIM, "exercise log")
            elif ev["kind"] == "test" and ev["title"] == "24-hour urine collection":
                if ending:
                    self.record(w, m1, self.urine_values(w, m1), SIM, "onboard urine test")
            elif ev["kind"] == "test" and started:
                self.record(
                    w, m1, self.test_values(w, ev["title"], m1), SIM, f"onboard {ev['title'].lower()}"
                )
        # once a day at midnight: bone model, nutrition log, mission month
        if int(m0 // M.DAY_MIN) != int(m1 // M.DAY_MIN):
            self.record(w, m1, self.bone_values(m1), "modeled", "bone loss model (Sibonga et al. 2015 rates)")
            self.record(w, m1, self.nutrition_values(w), SIM, "food and water log")
            if not self.hub.store.one(  # crew members who did not tap a mood today get a simulated one
                "SELECT 1 FROM tests WHERE astronaut_id=? AND key='mood.score' AND mission_minute>?",
                (aid, m1 - M.DAY_MIN),
            ):
                self.record(w, m1, {"mood.score": max(1, min(5, round(4 + w.rng.gauss(0, 0.6))))}, SIM,
                            "daily mood check-in (simulated)")

    def record(self, w: Wearer, m: float, values: dict[str, float], origin: str, source: str) -> None:
        if values:
            self.hub.add_measurements(w.astronaut_id, m, values, origin, source)

    def _days(self, m: float) -> float:
        return max(0.0, m / M.DAY_MIN)

    def test_values(self, w: Wearer, title: str, m: float) -> dict[str, float]:
        b, r, days = w.profile.get("baseline", {}), w.rng, self._days(m)
        debt = self._sleep_debt(w)
        if title == "Morning check":
            return {
                "bp.sys": round(b.get("bp.sys", 118) + r.gauss(0, 4)),
                "bp.dia": round(b.get("bp.dia", 76) + r.gauss(0, 3)),
                "mass.changePct": round(-0.05 * days + r.gauss(0, 0.15), 2),
                "pvt.meanRtMs": round(b.get("pvt.meanRtMs", 255) + 8 * debt + r.gauss(0, 6)),
                "pvt.lapses": max(0, round(b.get("pvt.lapses", 1) + 1.5 * debt + r.gauss(0, 0.8))),
                "back.pain": max(
                    0, min(10, round(b.get("back.pain", 0) + 3 * math.exp(-days / 3) + r.gauss(0, 0.5)))
                ),
            }
        if title == "Blood draw":
            return {
                "hemoglobin.gdl": round(b.get("hemoglobin.gdl", 14) - 0.02 * days + r.gauss(0, 0.15), 1),
                "vitd.ngml": round(b.get("vitd.ngml", 30) - 0.1 * days + r.gauss(0, 1.0), 1),
                "glucose.mgdl": round(b.get("glucose.mgdl", 90) + r.gauss(0, 5)),
                # the rest of the panel the dashboard shows: test signals around the pre-flight value
                **{
                    k: round(b.get(k, S.DASHBOARD_TEST_SIGNALS[k]) * (1 + r.gauss(0, 0.03)), 2)
                    for k in ("wbc.k", "platelets.k", "hematocrit.pct", "ferritin.ngml", "sodium.mmol",
                              "potassium.mmol", "creatinine.mgdl", "calcium.mgdl", "crp.mgl", "cortisol.ugdl")
                },
            }
        if title == "Fitness test":
            adherence = self._adherence(w, m)
            loss = 0.25 * days * (1 - adherence)
            return {
                "strength.changePct": round(-loss + r.gauss(0, 0.6), 1),
                "aerobic.changePct": round(-0.7 * loss + r.gauss(0, 0.6), 1),
            }
        return {}

    def urine_values(self, w: Wearer, m: float) -> dict[str, float]:
        b, r, days = w.profile.get("baseline", {}), w.rng, self._days(m)
        return {
            "urine.volumeL": round(b.get("urine.volumeL", 2.0) - 0.1 + r.gauss(0, 0.15), 2),
            "urine.calciumMgDay": round(b.get("urine.calciumMgDay", 180) + 1.5 * days + r.gauss(0, 10)),
            "urine.ph": round(b.get("urine.ph", 6.2) + r.gauss(0, 0.15), 1),
            "urine.citrateMgDay": round(b.get("urine.citrateMgDay", 640) + r.gauss(0, 30)),
        }

    def sleep_values(self, w: Wearer, ev: dict[str, Any]) -> dict[str, float]:
        rows = self.hub.store.bursts_between(w.astronaut_id, ev["m_start"], ev["m_end"])
        asleep = sum(1 for x in rows if x["state"] == "asleep") * S.MISSION_MINUTES_PER_BURST / 60
        # the wearable counts time asleep; a few short wake-ups are simulated
        hours = max(0.0, asleep - abs(w.rng.gauss(0.6, 0.4)))
        target = w.profile.get("sleep_target_h", 7.0)
        return {
            "sleep.hours": round(hours, 1),
            "sleep.quality": max(1, min(5, round(4 - max(0, target - hours)))),
        }

    def exercise_values(self, w: Wearer, m: float) -> dict[str, float]:
        d = M.day_of(m)
        week = [w.exercise_log.get(x, 0.0) for x in range(max(1, d - 6), d + 1)]
        per_week = sum(week) / len(week) * 7
        return {
            "exercise.minPerWeek": round(per_week),
            "exercise.resistiveDays": sum(1 for x in week if x > 0) * 7 // len(week),
        }

    def nutrition_values(self, w: Wearer) -> dict[str, float]:
        r = w.rng
        return {
            "nutrition.energyPct": round(90 + r.gauss(0, 7)),
            "nutrition.proteinGkg": round(1.3 + r.gauss(0, 0.15), 2),
            "nutrition.fluidL": round(2.3 + r.gauss(0, 0.3), 1),
        }

    def bone_values(self, m: float) -> dict[str, float]:
        months = self._days(m) / 30.0
        out = {k: round(-rate * months, 2) for k, rate in BONE_RATE_PCT_MONTH.items()}
        out["mission.month"] = round(months, 2)
        return out

    def _sleep_debt(self, w: Wearer) -> float:
        last = self.hub.store.latest_tests(w.astronaut_id).get("sleep.hours")
        return max(0.0, w.profile.get("sleep_target_h", 7.0) - last["value"]) if last else 0.0

    def _adherence(self, w: Wearer, m: float) -> float:
        d = M.day_of(m)
        days = [w.exercise_log.get(x, 0.0) for x in range(max(1, d - 3), d + 1)]
        return min(1.0, (sum(days) / max(1, len(days))) / S.EXERCISE_TARGET_MIN)


def preflight_values(profile: dict[str, Any]) -> dict[str, float]:
    """The values every tile starts from: the pre-flight report (changes vs. pre-flight start at 0)."""
    b = dict(profile.get("baseline", {}))
    b.update(
        {
            "hr.rest": profile["resting_hr"],
            "spo2.pct": profile["spo2"],
            "radiation.careerMsv": profile.get("prior_career_msv", 0.0),
        }
    )
    b.setdefault("sleep.hours", profile.get("sleep_target_h", 7.0))
    b.setdefault("mood.score", 4)
    # pre-flight training and diet plan (simulated) so the Sleep / Exercise / Nutrition scores start with data
    for k, v in (
        ("sleep.quality", 4),
        ("exercise.minPerWeek", 7 * S.EXERCISE_TARGET_MIN),
        ("exercise.resistiveDays", 6),
        ("nutrition.energyPct", 100),
        ("nutrition.proteinGkg", 1.3),
        ("nutrition.fluidL", 2.5),
    ):
        b.setdefault(k, v)
    for k, v in S.DASHBOARD_TEST_SIGNALS.items():  # every dashboard value has a starting point (test signals)
        b.setdefault(k, v)
    for k in (
        "mass.changePct",
        "strength.changePct",
        "aerobic.changePct",
        "bmd.hipPct",
        "bmd.lumbarPct",
        "bmd.wholeBodyPct",
        "mission.month",
        "radiation.eventMsv",
    ):
        b.setdefault(k, 0.0)
    return b
