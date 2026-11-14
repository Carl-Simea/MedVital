"""Spacecraft-hub settings: crew baselines, alert limits, demo scenarios.

Every number here says where it comes from:

* ``source="NASA ..."``  a cited NASA value;
* ``source="RAD ..."``    a cited Curiosity RAD measurement;
* ``source="demo"``      a demo setting chosen so the live demo is readable. NOT a clinical or
                          NASA value. Change it freely.

The observation modules (``medvital.modules``) stay threshold-free (CLAUDE.md rule 3). The alert
layer below is the team plan's RETURN_NOW / CHECK_VITALS / INFO logic and lives only in the hub
(docs/DECISIONS.md D-033).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# ---------------------------------------------------------------------------- demo time
BURST_SECONDS = 5  # the wearable sends one burst every 5 s (team plan)
MISSION_MINUTES_PER_BURST = 30  # demo clock: one burst stands for 30 min of mission time (source: demo)
BURSTS_PER_MISSION_DAY = 24 * 60 // MISSION_MINUTES_PER_BURST  # 48 bursts = 4 real minutes


@dataclass(frozen=True)
class Limit:
    value: float
    unit: str
    source: str
    note: str = ""


# ---------------------------------------------------------------------------- radiation limits
LIMITS: dict[str, Limit] = {
    "career_msv": Limit(
        600.0,
        "mSv",
        "NASA-STD-3001 Vol. 1 [V1 4030]",
        "Career effective-dose limit, universal for all ages and sexes.",
    ),
    "solar_event_msv": Limit(
        250.0,
        "mSv",
        "NASA-STD-3001 Vol. 1 [V1 4031]",
        "Short-term limit for one solar particle event.",
    ),
    "eva_msv": Limit(
        2.0,
        "mSv",
        "demo",
        "Dose budget for one spacewalk. Demo setting so the gauge moves during the demo.",
    ),
    "eva_dose_rate_usv_h": Limit(
        1000.0,
        "uSv/h",
        "demo",
        "Dose-rate ceiling during a spacewalk. Demo setting.",
    ),
    "eva_warn_fraction": Limit(0.8, "fraction", "demo", "RETURN_NOW once 80 % of the EVA budget is used."),
}

# ---------------------------------------------------------------------------- vitals allowances
# How far above the astronaut's OWN pre-flight resting heart rate a reading may go before the hub
# asks for a vitals check, by activity state. Personal-baseline-relative demo settings.
HR_ALLOWANCE_BPM: dict[str, float] = {"asleep": 25, "awake": 40, "exercise": 95, "spacewalk": 75}
SPO2_DROP_PCT = 4.0  # CHECK_VITALS when SpO2 falls this far below the astronaut's own baseline (demo)
CONFIRM_BURSTS = 2  # a vitals alert needs 2 bursts in a row (double-check against sensor glitches)
GLITCH_HR_JUMP_BPM = 60  # a jump this big in one 5-s burst is treated as a possible sensor glitch
PLAUSIBLE = {"heartRate": (25.0, 230.0), "spo2": (50.0, 100.0), "doseRate": (0.0, 1.0e6)}
CHECK_VITALS_COOLDOWN_S = 45  # do not re-buzz CHECK_VITALS for the same astronaut more often (demo)
SOLAR_EVENT_ACTIVE_S = 120  # how long a replayed solar event stays "active" in the demo

# Daily targets used for the summary and the exercise reminder.
EXERCISE_TARGET_MIN = 120  # NASA crews exercise about 2 h a day (source: demo, rounded)


# ---------------------------------------------------------------------------- crew baselines
@dataclass(frozen=True)
class CrewProfile:
    astronaut_id: str
    name: str
    role: str
    resting_hr: float  # bpm, from the pre-flight medical
    spo2: float  # %, pre-flight
    sleep_target_h: float
    prior_career_msv: float  # dose from earlier missions
    note: str = "Simulated pre-flight results (not a real person)."

    def to_json(self) -> dict:
        return asdict(self)


# Two different baselines so the demo shows the system adapting to each person.
CREW: tuple[CrewProfile, ...] = (
    CrewProfile(
        "astro-1",
        "Astronaut 1",
        "Commander",
        resting_hr=58,
        spo2=98,
        sleep_target_h=7.0,
        prior_career_msv=112.0,
    ),
    CrewProfile(
        "astro-2",
        "Astronaut 2",
        "Flight engineer",
        resting_hr=72,
        spo2=97,
        sleep_target_h=7.5,
        prior_career_msv=41.0,
    ),
)


def crew_profile(astronaut_id: str) -> CrewProfile | None:
    return next((c for c in CREW if c.astronaut_id == astronaut_id), None)


# ---------------------------------------------------------------------------- scenarios
# Ready-made numbers the astronaut tabs play back (team plan: Spacecraft -> astronaut tabs).
# Heart rate is an offset from each astronaut's own resting baseline, so profiles stay different.
MARS_SURFACE_USV_H = round(0.64 * 1000 / 24, 1)  # 26.7 uSv/h

SCENARIOS: dict[str, dict] = {
    "normal": {
        "label": "Normal day",
        "state": "awake",
        "hrOffset": [6, 4],
        "spo2Offset": [0, 0.6],
        "doseRate": [MARS_SURFACE_USV_H, 3.0],
        "source": "Dose rate: Curiosity RAD, Mars surface 0.64 mSv/day (Hassler et al., Science 2014). "
        "Heart rate and SpO2: simulated around the pre-flight baseline.",
    },
    "sleep": {
        "label": "Sleep",
        "state": "asleep",
        "hrOffset": [-6, 2],
        "spo2Offset": [-0.5, 0.5],
        "doseRate": [MARS_SURFACE_USV_H, 3.0],
        "source": "Simulated around the pre-flight baseline.",
    },
    "exercise": {
        "label": "Exercise",
        "state": "exercise",
        "hrOffset": [62, 6],
        "spo2Offset": [-0.5, 0.6],
        "doseRate": [MARS_SURFACE_USV_H, 3.0],
        "source": "Simulated.",
    },
    "spacewalk": {
        "label": "Spacewalk",
        "state": "spacewalk",
        "hrOffset": [28, 5],
        "spo2Offset": [-0.4, 0.5],
        # outside the habitat there is no shielding: about twice the surface rate (simulated)
        "doseRate": [MARS_SURFACE_USV_H * 2, 5.0],
        "source": "Simulated; base rate from Curiosity RAD.",
    },
    "hr_spike": {
        "label": "Heart-rate spike",
        "state": "awake",
        "hrOffset": [58, 4],
        "spo2Offset": [-5.5, 0.6],
        "doseRate": [MARS_SURFACE_USV_H, 3.0],
        "source": "Simulated problem for the demo.",
    },
    "solar_event": {
        "label": "Solar event",
        "state": None,
        "hrOffset": None,
        "spo2Offset": None,
        # multiplies the current scenario's dose rate while a solar particle event is active
        "doseFactor": 40,
        "shieldedFraction": 0.1,
        "source": "Simulated SPE spike (inside the habitat, shielding keeps 10 %); "
        "the event itself is replayed "
        "from NASA DONKI.",
    },
}


def public_config() -> dict:
    return {
        "burstSeconds": BURST_SECONDS,
        "missionMinutesPerBurst": MISSION_MINUTES_PER_BURST,
        "burstsPerMissionDay": BURSTS_PER_MISSION_DAY,
        "limits": {k: asdict(v) for k, v in LIMITS.items()},
        "hrAllowanceBpm": HR_ALLOWANCE_BPM,
        "spo2DropPct": SPO2_DROP_PCT,
        "exerciseTargetMin": EXERCISE_TARGET_MIN,
        "scenarios": SCENARIOS,
        "crew": [c.to_json() for c in CREW],
    }
