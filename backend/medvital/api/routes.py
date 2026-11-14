"""HTTP routes (API v1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from medvital.api.contracts import (
    HealthResponse,
    MetricDescriptor,
    ModuleAnalysis,
    ModuleDescriptor,
    ObservationList,
    ProfileDescriptor,
    SimulateRequest,
    SimulateResponse,
)
from medvital.core.observation import ModuleId
from medvital.core.provenance import DataOrigin
from medvital.db.repository import ObservationRepository
from medvital.ingest import ingest
from medvital.registry import MODULES, get_module
from medvital.simulated_profiles import PROFILES
from medvital.sync.protocol import SyncPullResponse, SyncPushRequest, SyncPushResponse

router = APIRouter(prefix="/api/v1")


def get_repo(request: Request) -> ObservationRepository:
    return request.app.state.repo  # type: ignore[no-any-return]


Repo = Annotated[ObservationRepository, Depends(get_repo)]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.get("/modules", response_model=list[ModuleDescriptor])
def list_modules() -> list[ModuleDescriptor]:
    return [
        ModuleDescriptor(
            id=m.id,
            title=m.title,
            description=m.description,
            metrics=[
                MetricDescriptor(
                    name=s.name,
                    unit=s.unit,
                    description=s.description,
                    allowed_origins=sorted(s.allowed_origins),
                    derived=s.is_derived,
                )
                for s in m.metrics
            ],
        )
        for m in MODULES.values()
    ]


@router.get("/profiles", response_model=list[ProfileDescriptor])
def list_profiles() -> list[ProfileDescriptor]:
    return [
        ProfileDescriptor(
            profile_id=p.profile_id, display_name=p.display_name, description=p.description
        )
        for p in PROFILES.values()
    ]


@router.post("/simulate", response_model=SimulateResponse)
def simulate(req: SimulateRequest, repo: Repo) -> SimulateResponse:
    profile = PROFILES.get(req.profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"unknown profile '{req.profile_id}'")
    module = get_module(req.module)
    base = module.simulate(profile, req.start, req.days, req.seed)
    everything = base + module.derive(base)
    result = None
    if req.store:
        result = ingest(repo, [o.model_dump(mode="json") for o in everything])
    return SimulateResponse(observations=everything, ingest=result)


@router.get("/observations", response_model=ObservationList)
def list_observations(
    repo: Repo,
    astronaut_id: str | None = None,
    module: ModuleId | None = None,
    metric: str | None = None,
    origin: DataOrigin | None = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> ObservationList:
    found = repo.query(
        astronaut_id=astronaut_id, module=module, metric=metric, origin=origin, limit=limit
    )
    return ObservationList(observations=found)


@router.get("/modules/{module_id}/summary", response_model=ModuleAnalysis)
def module_summary(module_id: ModuleId, astronaut_id: str, repo: Repo) -> ModuleAnalysis:
    module = get_module(module_id)
    stored = repo.query(astronaut_id=astronaut_id, module=module_id, limit=100_000)
    return ModuleAnalysis(
        summary=module.analyze(astronaut_id, stored),
        derived=module.derive(stored),
    )


@router.post("/sync/push", response_model=SyncPushResponse)
def sync_push(req: SyncPushRequest, repo: Repo) -> SyncPushResponse:
    return ingest(repo, req.observations)


@router.get("/sync/pull", response_model=SyncPullResponse)
def sync_pull(
    repo: Repo,
    cursor: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> SyncPullResponse:
    page = repo.changes_since(cursor, limit)
    return SyncPullResponse(
        observations=page.observations, next_cursor=page.next_cursor, has_more=page.has_more
    )
