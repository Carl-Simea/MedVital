"""API v1 routes. Contract documented in docs/ARCHITECTURE.md §4 and docs/api/openapi.json."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from medvital import __version__
from medvital.api.deps import get_registry, get_repository
from medvital.api.schemas import (
    HealthResponse,
    MetricInfo,
    ModuleInfo,
    ObservationBatch,
    ObservationBatchResponse,
    SimulationRequest,
    SimulationResponse,
)
from medvital.core.module_spec import ModuleRegistry
from medvital.core.schema import DataOrigin, HealthObservation, ModuleId, SubjectId
from medvital.core.summary import ModuleSummary
from medvital.core.sync import (
    MAX_PULL_LIMIT,
    ServerChange,
    SyncPullResponse,
    SyncPushRequest,
    SyncPushResponse,
)
from medvital.db.repository import ObservationRepository
from medvital.ingest import ingest_observation
from medvital.simulation.generator import generate_observations
from medvital.simulation.profiles import SIMULATED_PROFILES, SimulatedAstronautProfile, get_profile

router = APIRouter(prefix="/api/v1")

Repo = Annotated[ObservationRepository, Depends(get_repository)]
Registry = Annotated[ModuleRegistry, Depends(get_registry)]


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(request: Request) -> HealthResponse:
    return HealthResponse(version=__version__, repository=request.app.state.settings.repository)


@router.get("/modules", response_model=list[ModuleInfo], tags=["modules"])
def list_modules(registry: Registry) -> list[ModuleInfo]:
    return [
        ModuleInfo(
            module=spec.module_id,
            name=spec.name,
            description=spec.description,
            method_notes=spec.method_notes,
            metrics=[
                MetricInfo(
                    metric=m.metric,
                    unit=m.unit,
                    description=m.description,
                    non_negative=m.non_negative,
                    required_context=list(m.required_context),
                    optional_context=list(m.optional_context),
                )
                for m in spec.metrics
            ],
        )
        for spec in registry.modules()
    ]


@router.get("/modules/{module}/summary", response_model=ModuleSummary, tags=["modules"])
def module_summary(
    module: ModuleId,
    subject_id: Annotated[SubjectId, Query()],
    repo: Repo,
    registry: Registry,
) -> ModuleSummary:
    observations = repo.query(subject_id=subject_id, module=module, limit=100_000)
    return registry.get(module).summarize(subject_id, observations)


@router.get("/profiles", response_model=list[SimulatedAstronautProfile], tags=["profiles"])
def list_profiles() -> tuple[SimulatedAstronautProfile, ...]:
    return SIMULATED_PROFILES


@router.get("/profiles/{profile_id}", response_model=SimulatedAstronautProfile, tags=["profiles"])
def read_profile(profile_id: str) -> SimulatedAstronautProfile:
    profile = get_profile(profile_id)
    if profile is None:
        raise HTTPException(404, f"unknown simulated profile {profile_id!r}")
    return profile


@router.post("/profiles/{profile_id}/simulate", response_model=SimulationResponse, tags=["profiles"])
def simulate(
    profile_id: str, body: SimulationRequest, repo: Repo, registry: Registry
) -> SimulationResponse:
    profile = get_profile(profile_id)
    if profile is None:
        raise HTTPException(404, f"unknown simulated profile {profile_id!r}")
    if body.start.tzinfo is None:
        raise HTTPException(422, "start must be timezone-aware")
    observations = generate_observations(profile, body.start, body.days, body.seed)
    if body.persist:
        for obs in observations:
            ingest_observation(repo, registry, obs)
    return SimulationResponse(
        profile_id=profile_id, observations=observations, persisted=body.persist
    )


@router.post("/observations", response_model=ObservationBatchResponse, tags=["observations"])
def post_observations(
    body: ObservationBatch, repo: Repo, registry: Registry
) -> ObservationBatchResponse:
    return ObservationBatchResponse(
        results=[ingest_observation(repo, registry, o) for o in body.observations]
    )


@router.get("/observations", response_model=list[HealthObservation], tags=["observations"])
def get_observations(
    repo: Repo,
    subject_id: SubjectId | None = None,
    module: ModuleId | None = None,
    data_origin: DataOrigin | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=10_000)] = 1000,
) -> list[HealthObservation]:
    return repo.query(
        subject_id=subject_id,
        module=module,
        data_origin=data_origin,
        since=since,
        until=until,
        limit=limit,
    )


@router.post("/sync/push", response_model=SyncPushResponse, tags=["sync"])
def sync_push(body: SyncPushRequest, repo: Repo, registry: Registry) -> SyncPushResponse:
    results = [
        ingest_observation(repo, registry, m.observation, mutation_id=m.mutation_id)
        for m in body.mutations
    ]
    return SyncPushResponse(results=results, server_cursor=repo.head_seq())


@router.get("/sync/pull", response_model=SyncPullResponse, tags=["sync"])
def sync_pull(
    repo: Repo,
    cursor: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PULL_LIMIT)] = 500,
    subject_id: SubjectId | None = None,
) -> SyncPullResponse:
    # Read head BEFORE the page so rows inserted meanwhile are never skipped; at worst
    # the client re-receives a row, which is harmless because upserts are keyed by id.
    head = repo.head_seq()
    rows = repo.changes_since(cursor, limit=limit + 1, subject_id=subject_id)
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = page[-1].server_seq if has_more else max(head, page[-1].server_seq if page else 0, cursor)
    return SyncPullResponse(
        changes=[ServerChange(server_seq=r.server_seq, observation=r.observation) for r in page],
        next_cursor=next_cursor,
        has_more=has_more,
    )
