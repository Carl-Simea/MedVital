"""Fixed simulated astronaut profiles. None correspond to any real person."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from medvital.core.schema import DataOrigin, SubjectId

DISCLAIMER = (
    "Synthetic profile for software testing. Baseline values are arbitrary placeholders, "
    "not derived from any NASA dataset or real individual."
)


class SimulatedAstronautProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile_id: SubjectId
    label: str
    age_years: int
    planned_duration_days: int
    # Arbitrary placeholder baselines used only as signal centres by the generator.
    bone_bmd_baseline_g_cm2: float
    resting_hr_baseline_bpm: float
    rr_mean_ms: float
    sleep_hours_baseline: float
    self_report_baseline: float
    data_origin: Literal[DataOrigin.SIMULATED] = DataOrigin.SIMULATED
    disclaimer: str = DISCLAIMER


SIMULATED_PROFILES: tuple[SimulatedAstronautProfile, ...] = (
    SimulatedAstronautProfile(
        profile_id="SIM-A01", label="Simulated subject A01", age_years=40, planned_duration_days=180,
        bone_bmd_baseline_g_cm2=1.0, resting_hr_baseline_bpm=60.0, rr_mean_ms=1000.0,
        sleep_hours_baseline=7.0, self_report_baseline=5.0,
    ),
    SimulatedAstronautProfile(
        profile_id="SIM-A02", label="Simulated subject A02", age_years=45, planned_duration_days=180,
        bone_bmd_baseline_g_cm2=0.9, resting_hr_baseline_bpm=65.0, rr_mean_ms=900.0,
        sleep_hours_baseline=6.5, self_report_baseline=6.0,
    ),
    SimulatedAstronautProfile(
        profile_id="SIM-A03", label="Simulated subject A03", age_years=36, planned_duration_days=240,
        bone_bmd_baseline_g_cm2=1.1, resting_hr_baseline_bpm=55.0, rr_mean_ms=1100.0,
        sleep_hours_baseline=7.5, self_report_baseline=4.0,
    ),
    SimulatedAstronautProfile(
        profile_id="SIM-A04", label="Simulated subject A04", age_years=50, planned_duration_days=120,
        bone_bmd_baseline_g_cm2=0.8, resting_hr_baseline_bpm=70.0, rr_mean_ms=850.0,
        sleep_hours_baseline=6.0, self_report_baseline=5.0,
    ),
)


def get_profile(profile_id: str) -> SimulatedAstronautProfile | None:
    return next((p for p in SIMULATED_PROFILES if p.profile_id == profile_id), None)
