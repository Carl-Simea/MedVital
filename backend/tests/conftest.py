from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from medvital.core.observation import HealthObservation, ModuleId
from medvital.core.provenance import DataOrigin, Provenance

T0 = datetime(2030, 1, 1, tzinfo=UTC)


def sim_provenance(seed: int = 1) -> Provenance:
    return Provenance(origin=DataOrigin.SIMULATED, source="test", method="test_v1", seed=seed)


def make_obs(
    *,
    module: ModuleId = ModuleId.CARDIOVASCULAR,
    metric: str = "heart_rate",
    unit: str = "bpm",
    value: float = 60.0,
    day: int = 0,
    astronaut_id: str = "SIM-001",
    context: dict[str, str] | None = None,
    obs_id: UUID | None = None,
    provenance: Provenance | None = None,
) -> HealthObservation:
    return HealthObservation(
        id=obs_id or uuid4(),
        astronaut_id=astronaut_id,
        module=module,
        metric=metric,
        value=value,
        unit=unit,
        observed_at=T0 + timedelta(days=day),
        provenance=provenance or sim_provenance(),
        context=context or {},
    )


@pytest.fixture
def t0() -> datetime:
    return T0
