"""Helper for building MODELED observations with complete provenance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from medvital.core.observation import HealthObservation, ModuleId
from medvital.core.provenance import DataOrigin, Provenance
from medvital.core.simulation import deterministic_id


def make_modeled(
    *,
    module: ModuleId,
    astronaut_id: str,
    metric: str,
    value: float,
    unit: str,
    observed_at: datetime,
    method: str,
    inputs: Sequence[HealthObservation],
    context: Mapping[str, str] | None = None,
) -> HealthObservation:
    """Create a modeled observation whose id is a deterministic function of method + inputs."""
    input_ids = tuple(sorted((o.id for o in inputs), key=str))
    return HealthObservation(
        id=deterministic_id("modeled", method, metric, *input_ids),
        astronaut_id=astronaut_id,
        module=module,
        metric=metric,
        value=value,
        unit=unit,
        observed_at=observed_at,
        provenance=Provenance(
            origin=DataOrigin.MODELED,
            source=f"medvital.{module.value}",
            method=method,
            derived_from=input_ids,
        ),
        context=dict(context or {}),
    )
