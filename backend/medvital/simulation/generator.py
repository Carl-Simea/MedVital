"""Deterministic synthetic observation generator.

Same (profile, start, days, seed, params) -> byte-identical observations with identical
UUIDs (uuid5), so regenerating and re-syncing is idempotent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

import numpy as np

from medvital.core.schema import DataOrigin, HealthObservation, ModuleId, Provenance
from medvital.simulation.profiles import SimulatedAstronautProfile

GENERATOR_VERSION = "0.1.0"
_NAMESPACE = UUID("6f1c6a52-3b57-4f0e-9a49-5a5a2a0e0c11")
_NOTE = "Synthetic test signal with arbitrary magnitudes. Not derived from NASA data or any real person."


@dataclass(frozen=True)
class SimulationParameters:
    """Arbitrary signal shapes for exercising software. Not scientific parameters."""

    radiation_absorbed_mgy_per_day: float = 1.0
    radiation_quality_factor: float = 2.0
    bone_drift_fraction_per_day: float = -0.0001
    bone_interval_days: int = 14
    bone_site: str = "femoral_neck"
    rr_session_interval_days: int = 7
    rr_beats_per_session: int = 60
    noise_fraction: float = 0.05
    self_report_instrument: str = "SIM-INSTRUMENT-1"


def _provenance(seed: int) -> Provenance:
    return Provenance(
        data_origin=DataOrigin.SIMULATED,
        source="medvital.simulation.generator",
        generator_version=GENERATOR_VERSION,
        seed=seed,
        notes=_NOTE,
    )


def generate_observations(
    profile: SimulatedAstronautProfile,
    start: datetime,
    days: int,
    seed: int,
    params: SimulationParameters | None = None,
) -> list[HealthObservation]:
    if not 1 <= days <= 730:
        raise ValueError("days must be between 1 and 730")
    if start.tzinfo is None:
        raise ValueError("start must be timezone-aware")
    p = params or SimulationParameters()
    rng = np.random.default_rng(seed)
    prov = _provenance(seed)
    start = start.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    out: list[HealthObservation] = []

    def emit(module: ModuleId, metric: str, unit: str, value: float, at: datetime, context=None, key=""):
        out.append(
            HealthObservation(
                id=uuid5(_NAMESPACE, f"{profile.profile_id}|{seed}|{metric}|{at.isoformat()}|{key}"),
                subject_id=profile.profile_id,
                module=module,
                metric=metric,
                value=float(value),
                unit=unit,
                observed_at=at,
                recorded_at=at,
                context=context or {},
                provenance=prov,
            )
        )

    n = p.noise_fraction
    for day in range(days):
        at = start + timedelta(days=day)

        # Radiation (daily integrals)
        absorbed = max(0.0, p.radiation_absorbed_mgy_per_day * (1 + rng.normal(0, n)))
        equivalent = max(0.0, absorbed * p.radiation_quality_factor * (1 + rng.normal(0, n / 2)))
        emit(ModuleId.RADIATION, "radiation.absorbed_dose_daily", "mGy", absorbed, at)
        emit(ModuleId.RADIATION, "radiation.dose_equivalent_daily", "mSv", equivalent, at)

        # Bone (sparse)
        if day % p.bone_interval_days == 0:
            bmd = profile.bone_bmd_baseline_g_cm2 * (1 + p.bone_drift_fraction_per_day * day)
            bmd *= 1 + rng.normal(0, n / 5)
            emit(ModuleId.BONE, "bone.areal_bmd", "g/cm2", max(bmd, 0.0), at, {"site": p.bone_site})

        # Cardiovascular
        hr = max(1.0, profile.resting_hr_baseline_bpm + rng.normal(0, 2.0))
        emit(ModuleId.CARDIOVASCULAR, "cardiovascular.resting_heart_rate", "{beats}/min", hr, at)
        if day % p.rr_session_interval_days == 0:
            session = f"sim-d{day:03d}"
            t = at + timedelta(hours=8)
            rr = profile.rr_mean_ms * (1 + rng.normal(0, n, size=p.rr_beats_per_session))
            for i, value in enumerate(np.maximum(rr, 1.0)):
                emit(
                    ModuleId.CARDIOVASCULAR, "cardiovascular.rr_interval", "ms", value,
                    t + timedelta(seconds=i), {"session_id": session}, key=str(i),
                )

        # Behavioral
        sleep = max(0.0, profile.sleep_hours_baseline + rng.normal(0, 0.5))
        emit(ModuleId.BEHAVIORAL, "behavioral.sleep_duration", "h", sleep, at)
        score = profile.self_report_baseline + rng.normal(0, 1.0)
        emit(
            ModuleId.BEHAVIORAL, "behavioral.self_report_score", "{score}", score, at,
            {"instrument": p.self_report_instrument},
        )

    return out
