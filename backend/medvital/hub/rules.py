"""Alert rules and the double-check. Pure functions: numbers in, decisions out.

The rules decide when to alert; AI only words the explanation afterwards, so a slow or wrong AI
answer can never block a RETURN_NOW (team plan).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from medvital.hub import settings as S

RETURN_NOW, CHECK_VITALS, INFO = "RETURN_NOW", "CHECK_VITALS", "INFO"


@dataclass
class Check:
    quality: str  # valid | suspect | invalid
    note: str = ""


def double_check(burst: dict[str, Any], previous: dict[str, Any] | None) -> Check:
    """Is this burst believable? Sensor glitch or real problem?"""
    for name, (lo, hi) in S.PLAUSIBLE.items():
        v = burst.get(name)
        if not isinstance(v, (int, float)) or not lo <= v <= hi:
            return Check("invalid", f"{name}={v} is outside what a sensor can physically report ({lo}–{hi}).")
    if previous and previous["quality"] == "valid":
        if burst["totalDose"] + 1e-9 < previous["total_dose"]:
            return Check("suspect", "Running dose total went down: dosimeter reset or glitch.")
        jump = abs(burst["heartRate"] - previous["heart_rate"])
        if jump > S.GLITCH_HR_JUMP_BPM:
            return Check(
                "suspect",
                f"Heart rate jumped {jump:.0f} bpm in one burst: possible sensor glitch. "
                "Stored and flagged, no alert until the next burst confirms it.",
            )
    return Check("valid")


def eva_dose(history: list[dict[str, Any]]) -> tuple[float, int]:
    """Dose (mSv) since the current spacewalk began, and how many bursts it has lasted."""
    if not history or history[-1]["state"] != "spacewalk":
        return 0.0, 0
    i = len(history) - 1
    while i > 0 and history[i - 1]["state"] == "spacewalk":
        i -= 1
    start = history[i - 1]["total_dose"] if i > 0 else history[i]["total_dose"]
    return max(0.0, history[-1]["total_dose"] - start), len(history) - i


@dataclass
class Decision:
    code: str
    reason: str  # machine key: solar_event | eva_dose_rate | eva_budget | heart_rate | spo2
    message: str
    facts: dict[str, Any] = field(default_factory=dict)


def evaluate(history: list[dict[str, Any]], profile: dict[str, Any], solar_active: bool) -> list[Decision]:
    """``history``: this astronaut's recent bursts, oldest first, the new one last (store rows)."""
    out: list[Decision] = []
    b = history[-1]
    if b["quality"] == "invalid":
        return out
    state = b["state"]

    # --- radiation first: RETURN_NOW only matters outside -------------------------------------
    if state == "spacewalk":
        dose, n = eva_dose(history)
        budget = S.LIMITS["eva_msv"].value
        pct = 100 * dose / budget
        facts = {
            "evaDoseMsv": round(dose, 3),
            "evaBudgetMsv": budget,
            "evaPct": round(pct, 1),
            "doseRate": b["dose_rate"],
            "evaMinutes": n * S.MISSION_MINUTES_PER_BURST,
        }
        if solar_active:
            out.append(
                Decision(
                    RETURN_NOW,
                    "solar_event",
                    f"There's a solar event right now. You've used {pct:.0f}% of your radiation "
                    "budget for this spacewalk. Head back in.",
                    facts,
                )
            )
        elif b["dose_rate"] > S.LIMITS["eva_dose_rate_usv_h"].value:
            out.append(
                Decision(
                    RETURN_NOW,
                    "eva_dose_rate",
                    f"Radiation is {b['dose_rate']:.0f} µSv/h, above the spacewalk ceiling of "
                    f"{S.LIMITS['eva_dose_rate_usv_h'].value:.0f}. Head back in.",
                    facts,
                )
            )
        elif dose >= S.LIMITS["eva_warn_fraction"].value * budget:
            out.append(
                Decision(
                    RETURN_NOW,
                    "eva_budget",
                    f"You've used {pct:.0f}% of your radiation budget for this spacewalk. Head back in.",
                    facts,
                )
            )

    # --- vitals: personal baseline, confirmed over CONFIRM_BURSTS valid bursts ----------------
    if b["quality"] != "valid":
        return out
    recent = [h for h in history[-S.CONFIRM_BURSTS :] if h["quality"] == "valid"]
    confirmed = len(recent) == S.CONFIRM_BURSTS and all(h["state"] == state for h in recent)
    base_hr, base_spo2 = profile["resting_hr"], profile["spo2"]
    ceiling = base_hr + S.HR_ALLOWANCE_BPM.get(state, 40)
    if confirmed and all(h["heart_rate"] > ceiling for h in recent):
        out.append(
            Decision(
                CHECK_VITALS,
                "heart_rate",
                f"Heart rate {b['heart_rate']:.0f} bpm while {state}, well above your baseline of "
                f"{base_hr:.0f} bpm (confirmed over {S.CONFIRM_BURSTS} readings). "
                "Stop, rest and check in with the crew.",
                {"heartRate": b["heart_rate"], "baseline": base_hr, "ceiling": ceiling},
            )
        )
    floor = base_spo2 - S.SPO2_DROP_PCT
    if confirmed and all(h["spo2"] < floor for h in recent):
        out.append(
            Decision(
                CHECK_VITALS,
                "spo2",
                f"Blood oxygen {b['spo2']:.0f}% is below your baseline of {base_spo2:.0f}%. "
                "Check your suit or cabin air and breathe slowly.",
                {"spo2": b["spo2"], "baseline": base_spo2, "floor": floor},
            )
        )
    return out


def day_facts(bursts: list[dict[str, Any]], profile: dict[str, Any], alerts: int) -> dict[str, Any]:
    """Numbers for one mission day (each burst = MISSION_MINUTES_PER_BURST)."""
    m = S.MISSION_MINUTES_PER_BURST
    valid = [b for b in bursts if b["quality"] == "valid"]
    awake_hr = [b["heart_rate"] for b in valid if b["state"] == "awake"]
    asleep_hr = [b["heart_rate"] for b in valid if b["state"] == "asleep"]
    sleep_h = sum(1 for b in valid if b["state"] == "asleep") * m / 60
    exercise_min = sum(1 for b in valid if b["state"] == "exercise") * m
    eva_min = sum(1 for b in valid if b["state"] == "spacewalk") * m
    dose = (valid[-1]["total_dose"] - valid[0]["total_dose"]) if len(valid) > 1 else 0.0
    return {
        "bursts": len(bursts),
        "flagged": len(bursts) - len(valid),
        "sleepHours": round(sleep_h, 1),
        "sleepTargetHours": profile["sleep_target_h"],
        "sleepDebtHours": round(max(0.0, profile["sleep_target_h"] - sleep_h), 1),
        "exerciseMinutes": exercise_min,
        "exerciseTargetMinutes": S.EXERCISE_TARGET_MIN,
        "spacewalkMinutes": eva_min,
        "avgAwakeHr": round(sum(awake_hr) / len(awake_hr), 1) if awake_hr else None,
        "avgSleepHr": round(sum(asleep_hr) / len(asleep_hr), 1) if asleep_hr else None,
        "baselineHr": profile["resting_hr"],
        "minSpo2": min((b["spo2"] for b in valid), default=None),
        "doseMsv": round(max(0.0, dose), 3),
        "totalDoseMsv": round(valid[-1]["total_dose"], 3) if valid else None,
        "alerts": alerts,
    }


def summary_text(name: str, day: int, f: dict[str, Any]) -> str:
    """Template wording. AI may rephrase it; the onboard agent checks the numbers survive."""
    parts = [f"{name}, mission day {day}."]
    if f["sleepHours"]:
        debt = (
            f" ({f['sleepDebtHours']} h short of your {f['sleepTargetHours']} h target)"
            if f["sleepDebtHours"]
            else ""
        )
        parts.append(f"Slept {f['sleepHours']} h{debt}.")
    else:
        parts.append("No sleep recorded today.")
    if f["avgAwakeHr"] is not None:
        parts.append(f"Average awake heart rate {f['avgAwakeHr']} bpm (baseline {f['baselineHr']}).")
    if f["minSpo2"] is not None:
        parts.append(f"Lowest blood oxygen {f['minSpo2']:.0f}%.")
    parts.append(f"Exercise {f['exerciseMinutes']:.0f} of {f['exerciseTargetMinutes']:.0f} min.")
    if f["spacewalkMinutes"]:
        parts.append(f"Spacewalk {f['spacewalkMinutes']:.0f} min.")
    parts.append(f"Radiation today {f['doseMsv']} mSv.")
    if f["alerts"]:
        parts.append(f"{f['alerts']} alert(s) today.")
    return " ".join(parts)


def exercise_tip(f: dict[str, Any]) -> str:
    short = f["exerciseTargetMinutes"] - f["exerciseMinutes"]
    if short > 0:
        return (
            f"Do {short:.0f} more minutes of exercise: resistance work "
            "(squats, deadlifts on the resistive device) "
            "loads your hips and spine, where bone is lost fastest, "
            "and the treadmill or bike keeps your heart fit."
        )
    return "Exercise target met. Keep mixing resistance work (bone and muscle) with cardio."
