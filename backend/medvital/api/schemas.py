"""Response/request models that exist only at the HTTP boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from medvital.core.schema import HealthObservation, ModuleId
from medvital.core.sync import MutationResult
from medvital.simulation.generator import GENERATOR_VERSION


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    repository: str


class MetricInfo(BaseModel):
    metric: str
    unit: str
    description: str
    non_negative: bool
    required_context: list[str]
    optional_context: list[str]


class ModuleInfo(BaseModel):
    module: ModuleId
    name: str
    description: str
    method_notes: str
    metrics: list[MetricInfo]


class ObservationBatch(BaseModel):
    observations: list[HealthObservation] = Field(max_length=500)


class ObservationBatchResponse(BaseModel):
    results: list[MutationResult]


class TelemetryBatch(BaseModel):
    """Raw event objects, validated one by one so a single bad event cannot block a batch.
    The event shape is documented by ``GET /api/v1/telemetry/schema`` (``TelemetryEvent``)."""

    events: list[dict[str, Any]] = Field(max_length=500)


class RejectionOut(BaseModel):
    rejection_id: int
    received_at: datetime
    source: str
    device_id: str | None
    reason: str
    payload: dict[str, Any]


class SimulationRequest(BaseModel):
    start: datetime = Field(description="Timezone-aware start; truncated to 00:00 UTC.")
    days: int = Field(ge=1, le=730)
    seed: int = 0
    persist: bool = Field(
        default=False, description="Also store the generated observations on the server."
    )


class SimulationResponse(BaseModel):
    profile_id: str
    generator_version: str = GENERATOR_VERSION
    observations: list[HealthObservation]
    persisted: bool
