"""Spacecraft-hub settings: mission timeline, crew baselines, alert limits, data sources.

Every number says where it comes from:

* ``source="NASA ..."`` / a paper  a cited value;
* ``source="demo"``  a demo setting so a live presentation is readable. NOT a clinical or NASA value.

The observation modules (``medvital.modules``) stay threshold-free (CLAUDE.md rule 3). The alert layer below
lives only in the hub (docs/DECISIONS.md D-033, D-034).
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO = Path(os.environ.get("MEDVITAL_REPO_ROOT", Path(__file__).resolve().parents[3]))
DATA = REPO / "data" / "nasa"
REPORTS = REPO / "reports"

# ---------------------------------------------------------------------------- demo time
# One real minute is one mission day (demo setting). Every wearable sends one burst per real second,
# so one burst covers 24 mission minutes and a mission day has 60 bursts.
DAY_SECONDS = float(os.environ.get("MEDVITAL_DAY_SECONDS", "60"))

# ---- Cloudflare link to Earth (cloudflare/ Worker + D1 + Workers AI). Both unset = local mode.
# The key is a secret: environment / Codespaces secret / gitignored .env only, never in the repo.
CLOUDFLARE_URL = os.environ.get("MEDVITAL_CLOUDFLARE_URL", "")
CLOUDFLARE_KEY = os.environ.get("MEDVITAL_CLOUDFLARE_KEY", "")
BURST_SECONDS = 1.0
MISSION_MINUTES_PER_BURST = 24 * 60 * BURST_SECONDS / DAY_SECONDS
BURSTS_PER_MISSION_DAY = round(DAY_SECONDS / BURST_SECONDS)

# Mission timeline: cruise to Mars, landing, surface operations (demo lengths).
CRUISE_DAYS = 8  # mission days 1..8 in the transit vehicle
LANDING_DAY = 9  # Mars landing at 06:00 on day 9; surface operations from then on
LANDING_HOUR = 6.0
MISSION_DAYS = 60  # the schedule is generated this far ahead

# Real space weather is replayed onto the mission calendar: mission day 1 00:00 = this UTC instant.
DONKI_FILE = DATA / "donki_2024-05-01_2024-06-29.json"
DONKI_EPOCH = "2024-05-01T00:00:00+00:00"
SEP_ACTIVE_HOURS = 12.0  # DONKI SEP records have no end time; an SEP counts as active this long (demo)
SEP_DOSE_FACTOR = 40.0  # simulated dose multiplier while an SEP is active outside shielding (demo)
SEP_SHIELDED_FRACTION = 0.1  # inside the habitat/storm shelter (demo)

# Curiosity RAD: real dose rates (tissue-equivalent detector E, uGy/h) from data/nasa/rad_dose.csv.
RAD_FILE = DATA / "rad_dose.csv"
# Mean quality factors measured by RAD turn absorbed dose into dose equivalent (Hassler et al., Science 2014).
QUALITY_FACTOR = {"cruise": 3.82, "surface": 3.05}
# Published means used only if rad_dose.csv is missing (Zeitlin et al. 2013; Hassler et al. 2014), uGy/h.
RAD_FALLBACK_UGY_H = {"cruise": 0.48 * 1000 / 24, "surface": 0.21 * 1000 / 24}
HABITAT_SHIELDING = 0.8  # surface habitat vs. RAD on the open surface (demo)

# Daily plan (mission time, hours). Sleep 23:00-07:00, exercise per astronaut, EVAs on surface days.
SLEEP_START_H, SLEEP_END_H = 23.0, 7.0
EVA_START_H, EVA_END_H = 10.0, 14.0
BLACKOUT_START_H, BLACKOUT_END_H = 2.0, 4.5  # surface: Earth not in view (simulated)


@dataclass(frozen=True)
class Limit:
    value: float
    unit: str
    source: str
    note: str = ""


LIMITS: dict[str, Limit] = {
    "career_msv": Limit(600.0, "mSv", "NASA-STD-3001 Vol. 1 [V1 4030]", "Career effective-dose limit."),
    "solar_event_msv": Limit(
        250.0, "mSv", "NASA-STD-3001 Vol. 1 [V1 4031]", "Limit for one solar particle event."
    ),
    "eva_msv": Limit(2.0, "mSv", "demo", "Dose budget for one spacewalk."),
    "eva_dose_rate_usv_h": Limit(1000.0, "uSv/h", "demo", "Dose-rate ceiling during a spacewalk."),
    "eva_warn_fraction": Limit(0.8, "fraction", "demo", "RETURN_NOW once 80 % of the EVA budget is used."),
}

HR_ALLOWANCE_BPM: dict[str, float] = {"asleep": 25, "awake": 40, "exercise": 95, "spacewalk": 75}
SPO2_DROP_PCT = 4.0
CONFIRM_BURSTS = 2
GLITCH_HR_JUMP_BPM = 60
PLAUSIBLE = {"heartRate": (25.0, 230.0), "spo2": (50.0, 100.0), "doseRate": (0.0, 1.0e6)}
CHECK_VITALS_COOLDOWN_S = 20  # real seconds (about 8 mission hours)
SOLAR_EVENT_ACTIVE_S = 30  # a demo replay stays active this many real seconds (half a mission day)
EXERCISE_TARGET_MIN = 120  # about 2 h a day (demo, rounded)
OFFLINE_AFTER_S = 3.0  # a wearable silent this long shows as disconnected


# ---------------------------------------------------------------------------- crew
@dataclass(frozen=True)
class CrewProfile:
    """Pre-flight baseline. Keys in ``baseline`` use the 3D body dashboard's indicator names."""

    astronaut_id: str
    name: str
    role: str
    age: int
    sex: str  # "f" | "m"
    height_cm: float
    weight_kg: float
    resting_hr: float
    spo2: float
    sleep_target_h: float
    prior_career_msv: float
    exercise_hour: float = 17.0  # daily exercise session start (mission time)
    baseline: dict[str, float] = field(default_factory=dict)
    report: str | None = None  # file stem in reports/
    note: str = "Fictional astronaut. Pre-flight values are simulated."

    def to_json(self) -> dict:
        return asdict(self)


def _b(**kw: float) -> dict[str, float]:
    return {k.replace("__", "."): v for k, v in kw.items()}


CREW: tuple[CrewProfile, ...] = (
    CrewProfile(
        "astro-1",
        "Maya Okafor",
        "Commander",
        44,
        "f",
        168,
        63,
        58,
        98,
        7.0,
        112.0,
        6.5,
        _b(
            bp__sys=112,
            bp__dia=72,
            resp__rate=13,
            temp__c=36.6,
            glucose__mgdl=86,
            hemoglobin__gdl=13.8,
            vitd__ngml=34,
            urine__volumeL=2.2,
            urine__calciumMgDay=165,
            pvt__meanRtMs=248,
            pvt__lapses=1,
            back__pain=0,
            sleep__hours=7.1,
        ),
        "astro-1_maya-okafor",
    ),
    CrewProfile(
        "astro-2",
        "Daniel Reyes",
        "Pilot",
        39,
        "m",
        181,
        82,
        66,
        97,
        7.5,
        41.0,
        17.0,
        _b(
            bp__sys=121,
            bp__dia=79,
            resp__rate=14,
            temp__c=36.7,
            glucose__mgdl=92,
            hemoglobin__gdl=15.1,
            vitd__ngml=29,
            urine__volumeL=2.0,
            urine__calciumMgDay=190,
            pvt__meanRtMs=262,
            pvt__lapses=2,
            back__pain=1,
            sleep__hours=7.4,
        ),
        "astro-2_daniel-reyes",
    ),
    CrewProfile(
        "astro-3",
        "Aiko Tanaka",
        "Flight surgeon",
        36,
        "f",
        160,
        55,
        61,
        98,
        7.5,
        0.0,
        12.0,
        _b(
            bp__sys=108,
            bp__dia=68,
            resp__rate=14,
            temp__c=36.5,
            glucose__mgdl=84,
            hemoglobin__gdl=13.2,
            vitd__ngml=38,
            urine__volumeL=2.4,
            urine__calciumMgDay=150,
            pvt__meanRtMs=241,
            pvt__lapses=0,
            back__pain=0,
            sleep__hours=7.6,
        ),
        "astro-3_aiko-tanaka",
    ),
    CrewProfile(
        "astro-4",
        "Jean-Luc Pierre",
        "Mission specialist",
        41,
        "m",
        176,
        78,
        72,
        97,
        7.0,
        68.0,
        19.0,
        _b(
            bp__sys=126,
            bp__dia=82,
            resp__rate=15,
            temp__c=36.8,
            glucose__mgdl=95,
            hemoglobin__gdl=14.9,
            vitd__ngml=26,
            urine__volumeL=1.9,
            urine__calciumMgDay=205,
            pvt__meanRtMs=270,
            pvt__lapses=2,
            back__pain=1,
            sleep__hours=6.8,
        ),
        "astro-4_jean-luc-pierre",
    ),
)

# Who goes on which surface spacewalk (pairs alternate). Day numbers are mission days.
EVA_PLAN = {
    10: ("astro-1", "astro-2"),
    12: ("astro-3", "astro-4"),
    14: ("astro-1", "astro-4"),
    16: ("astro-2", "astro-3"),
    18: ("astro-1", "astro-2"),
    20: ("astro-3", "astro-4"),
}


def crew_profile(astronaut_id: str) -> CrewProfile | None:
    return next((c for c in CREW if c.astronaut_id == astronaut_id), None)


# ---------------------------------------------------------------------------- demo scenarios
# Overrides the astronaut view's Demo drawer can switch on for one astronaut.
SCENARIOS: dict[str, dict] = {
    "auto": {"label": "Follow the mission plan"},
    "spacewalk": {"label": "Spacewalk now", "state": "spacewalk"},
    "exercise": {"label": "Exercise now", "state": "exercise"},
    "sleep": {"label": "Sleep now", "state": "asleep"},
    "hr_spike": {"label": "Heart-rate spike", "hrOffset": 58, "spo2Offset": -5.5},
}


def public_config() -> dict:
    return {
        "daySeconds": DAY_SECONDS,
        "burstSeconds": BURST_SECONDS,
        "missionMinutesPerBurst": MISSION_MINUTES_PER_BURST,
        "burstsPerMissionDay": BURSTS_PER_MISSION_DAY,
        "cruiseDays": CRUISE_DAYS,
        "landingDay": LANDING_DAY,
        "limits": {k: asdict(v) for k, v in LIMITS.items()},
        "hrAllowanceBpm": HR_ALLOWANCE_BPM,
        "spo2DropPct": SPO2_DROP_PCT,
        "exerciseTargetMin": EXERCISE_TARGET_MIN,
        "qualityFactor": QUALITY_FACTOR,
        "scenarios": SCENARIOS,
        "crew": [c.to_json() for c in CREW],
    }
