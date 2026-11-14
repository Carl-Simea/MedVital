from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from medvital.config import Settings
from medvital.core.schema import DataOrigin, HealthObservation, ModuleId, Provenance
from medvital.main import create_app

T0 = datetime(2030, 1, 1, tzinfo=UTC)  # arbitrary fixed test date


def simulated_provenance(seed: int = 1) -> Provenance:
    return Provenance(
        data_origin=DataOrigin.SIMULATED, source="pytest", generator_version="test", seed=seed
    )


def measured_provenance() -> Provenance:
    return Provenance(
        data_origin=DataOrigin.MEASURED, source="pytest-instrument", source_ref="test://fixture/1"
    )


def make_obs(
    metric: str = "radiation.absorbed_dose_daily",
    value: float = 1.0,
    *,
    module: ModuleId | None = None,
    unit: str | None = None,
    day: float = 0,
    subject_id: str = "SIM-T01",
    context: dict[str, str] | None = None,
    provenance: Provenance | None = None,
    id=None,
) -> HealthObservation:
    units = {
        "radiation.absorbed_dose_daily": "mGy",
        "radiation.dose_equivalent_daily": "mSv",
        "bone.areal_bmd": "g/cm2",
        "cardiovascular.resting_heart_rate": "{beats}/min",
        "cardiovascular.rr_interval": "ms",
        "behavioral.sleep_duration": "h",
        "behavioral.self_report_score": "{score}",
    }
    at = T0 + timedelta(days=day)
    return HealthObservation(
        id=id or uuid4(),
        subject_id=subject_id,
        module=module or ModuleId(metric.split(".")[0]),
        metric=metric,
        value=value,
        unit=unit or units[metric],
        observed_at=at,
        recorded_at=at,
        context=context or {},
        provenance=provenance or simulated_provenance(),
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(repository="memory")))
