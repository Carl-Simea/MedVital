"""Request and response models: the HTTP API contract (v1)."""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, Field

from medvital import __version__
from medvital.core.analysis import ModuleSummary
from medvital.core.observation import SCHEMA_VERSION, HealthObservation, ModuleId
from medvital.core.provenance import DataOrigin
from medvital.sync.protocol import SyncPushResponse


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = __version__
    observation_schema_version: int = SCHEMA_VERSION


class MetricDescriptor(BaseModel):
    name: str
    unit: str
    description: str
    allowed_origins: list[DataOrigin]
    derived: bool


class ModuleDescriptor(BaseModel):
    id: ModuleId
    title: str
    description: str
    metrics: list[MetricDescriptor]


class ProfileDescriptor(BaseModel):
    profile_id: str
    display_name: str
    description: str
    is_simulated: bool = True


class SimulateRequest(BaseModel):
    profile_id: str
    module: ModuleId
    start: AwareDatetime
    days: int = Field(ge=1, le=365)
    seed: int = Field(ge=0, le=2**32 - 1)
    # Persist the generated observations through the normal ingest path.
    store: bool = False


class SimulateResponse(BaseModel):
    observations: list[HealthObservation]
    ingest: SyncPushResponse | None = None


class ObservationList(BaseModel):
    observations: list[HealthObservation]


class ModuleAnalysis(BaseModel):
    summary: ModuleSummary
    # Modeled observations computed on the fly from stored base observations (not persisted).
    derived: list[HealthObservation]
