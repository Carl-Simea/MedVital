"""Simulated astronaut profiles.

These are parameter sets for the simulator, NOT real people and NOT derived from any NASA
dataset. Numbers are illustrative developer choices so that simulated series are plausible in
scale and easy to tell apart in demos. Every drift is zero: no spaceflight effect is assumed.
"""

from __future__ import annotations

from medvital.core.profiles import AstronautProfile, SimParameter

_BASE: dict[str, tuple[float, float]] = {
    # metric: (mean, sd)
    "absorbed_dose_rate": (100.0, 10.0),
    "bmd_areal": (1.0, 0.01),
    "heart_rate": (65.0, 5.0),
    "systolic_bp": (120.0, 6.0),
    "diastolic_bp": (80.0, 4.0),
    "hrv_rmssd": (40.0, 8.0),
    "sleep_duration": (7.0, 0.5),
    "self_reported_stress": (3.0, 1.0),
}


def _profile(
    profile_id: str,
    display_name: str,
    description: str,
    mean_scale: dict[str, float] | None = None,
) -> AstronautProfile:
    scale = mean_scale or {}
    return AstronautProfile(
        profile_id=profile_id,
        display_name=display_name,
        description=description,
        parameters={
            metric: SimParameter(mean=mean * scale.get(metric, 1.0), sd=sd)
            for metric, (mean, sd) in _BASE.items()
        },
    )


PROFILES: dict[str, AstronautProfile] = {
    p.profile_id: p
    for p in (
        _profile(
            "SIM-001", "Simulated A", "Reference parameter set. Simulated; not a real person."
        ),
        _profile(
            "SIM-002",
            "Simulated B",
            "Higher resting heart rate, lower sleep. Simulated; not a real person.",
            {"heart_rate": 1.1, "sleep_duration": 0.9},
        ),
        _profile(
            "SIM-003",
            "Simulated C",
            "Lower bone density parameter, higher dose rate. Simulated; not a real person.",
            {"bmd_areal": 0.9, "absorbed_dose_rate": 1.2},
        ),
        _profile(
            "SIM-004",
            "Simulated D",
            "Higher stress score, higher HRV. Simulated; not a real person.",
            {"self_reported_stress": 1.4, "hrv_rmssd": 1.15},
        ),
    )
}
