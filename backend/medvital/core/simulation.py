"""Seeded, reproducible simulation of observations from an AstronautProfile.

Output is always labelled ``DataOrigin.SIMULATED``. The generator is Gaussian noise around a
profile mean with an optional linear drift (zero by default). It makes no claim about real
physiology or real spaceflight data.
"""

from __future__ import annotations

import zlib
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

import numpy as np

from medvital.core.metrics import MetricSpec
from medvital.core.observation import HealthObservation, ModuleId
from medvital.core.profiles import AstronautProfile
from medvital.core.provenance import DataOrigin, Provenance

# Fixed namespace so simulated and modeled ids are deterministic across runs and machines.
ID_NAMESPACE = UUID("6f1f2b0e-8a43-4b6e-9a53-3d5c1f0a7e21")

SIM_SOURCE = "medvital.simulation.gaussian"
SIM_METHOD = "gaussian_noise_with_linear_drift_v1"


def deterministic_id(*parts: object) -> UUID:
    return uuid5(ID_NAMESPACE, ":".join(str(p) for p in parts))


def simulate_observations(
    *,
    profile: AstronautProfile,
    module: ModuleId,
    specs: Sequence[MetricSpec],
    context: Mapping[str, str],
    start: datetime,
    days: int,
    seed: int,
) -> list[HealthObservation]:
    """Generate simulated observations for every non-derived metric in ``specs``."""
    if start.tzinfo is None:
        raise ValueError("start must be timezone-aware")
    if days < 1:
        raise ValueError("days must be at least 1")
    start_utc = start.astimezone(UTC)
    out: list[HealthObservation] = []
    for spec in specs:
        if spec.is_derived:
            continue
        param = profile.parameters.get(spec.name)
        if param is None:
            raise ValueError(f"profile {profile.profile_id} has no parameters for {spec.name}")
        rng = np.random.default_rng(
            [seed, zlib.crc32(profile.profile_id.encode()), zlib.crc32(spec.name.encode())]
        )
        for day in range(0, days, spec.sim_cadence_days):
            value = param.mean + param.drift_per_day * day + float(rng.normal(0.0, param.sd))
            if spec.physical_min is not None:
                value = max(value, spec.physical_min)
            if spec.physical_max is not None:
                value = min(value, spec.physical_max)
            out.append(
                HealthObservation(
                    id=deterministic_id("sim", profile.profile_id, spec.name, day, seed, start_utc),
                    astronaut_id=profile.profile_id,
                    module=module,
                    metric=spec.name,
                    value=value,
                    unit=spec.unit,
                    observed_at=start_utc + timedelta(days=day),
                    provenance=Provenance(
                        origin=DataOrigin.SIMULATED,
                        source=SIM_SOURCE,
                        method=SIM_METHOD,
                        seed=seed,
                    ),
                    context=dict(context),
                )
            )
    return out
