"""API v1 routes. Contract documented in docs/ARCHITECTURE.md §4 and docs/api/openapi.json."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from medvital import __version__
from medvital.api.deps import get_principal, get_registry, get_repository, get_schedule_repository
from medvital.api.guards import (
    crews,
    need,
    need_station,
    need_subject,
    need_subject_filter,
    write_authorizer,
)
from medvital.api.schemas import (
    HealthResponse,
    MetricInfo,
    ModuleInfo,
    ObservationBatch,
    ObservationBatchResponse,
    RejectionOut,
    SimulationRequest,
    SimulationResponse,
    TelemetryBatch,
)
from medvital.authz import Permission, Principal, can_access_subject, visible_subjects
from medvital.core.module_spec import ModuleRegistry
from medvital.core.schedule import (
    MeasurementSchedule,
    MissionWindow,
    ResolvedEvent,
    ScheduleCoverage,
    resolve_schedule,
    schedule_coverage,
)
from medvital.core.schema import DataOrigin, HealthObservation, ModuleId, SubjectId
from medvital.core.summary import ModuleSummary
from medvital.core.sync import (
    MAX_PULL_LIMIT,
    ServerChange,
    SyncPullResponse,
    SyncPushRequest,
    SyncPushResponse,
)
from medvital.core.telemetry import TelemetryEvent, TelemetryResponse
from medvital.db.repository import ObservationRepository, ScheduleRepository
from medvital.ingest import ingest_observation
from medvital.live import LiveResponse, build_live
from medvital.schedules import ScheduleWriteResult, store_schedule
from medvital.simulation.generator import generate_observations
from medvital.simulation.profiles import SIMULATED_PROFILES, SimulatedAstronautProfile, get_profile
from medvital.telemetry import ingest_telemetry

router = APIRouter(prefix="/api/v1")

Repo = Annotated[ObservationRepository, Depends(get_repository)]
Registry = Annotated[ModuleRegistry, Depends(get_registry)]
Schedules = Annotated[ScheduleRepository, Depends(get_schedule_repository)]
Caller = Annotated[Principal, Depends(get_principal)]


def _crews(repo) -> dict[str, list[str]]:
    return crews(repo)


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
    caller: Caller,
) -> ModuleSummary:
    if not caller.can(Permission.READ_ANALYSIS) or not can_access_subject(caller, subject_id, _crews(repo)):
        raise HTTPException(status_code=403, detail="subject is outside this principal's scope")
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
    profile_id: str,
    body: SimulationRequest,
    repo: Repo,
    registry: Registry,
    caller: Caller,
) -> SimulationResponse:
    profile = get_profile(profile_id)
    if profile is None:
        raise HTTPException(404, f"unknown simulated profile {profile_id!r}")
    if body.start.tzinfo is None:
        raise HTTPException(422, "start must be timezone-aware")
    observations = generate_observations(profile, body.start, body.days, body.seed)
    if body.persist:
        need_station(caller, "persisting simulated observations")
        for obs in observations:
            ingest_observation(repo, registry, obs, channel="simulation")
    return SimulationResponse(profile_id=profile_id, observations=observations, persisted=body.persist)


@router.post("/observations", response_model=ObservationBatchResponse, tags=["observations"])
def post_observations(
    body: ObservationBatch,
    repo: Repo,
    registry: Registry,
    caller: Caller,
) -> ObservationBatchResponse:
    authorize = write_authorizer(caller, repo)
    return ObservationBatchResponse(
        results=[ingest_observation(repo, registry, o, authorize=authorize) for o in body.observations]
    )


@router.get("/observations", response_model=list[HealthObservation], tags=["observations"])
def get_observations(
    repo: Repo,
    caller: Caller,
    subject_id: SubjectId | None = None,
    module: ModuleId | None = None,
    data_origin: DataOrigin | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=10_000)] = 1000,
) -> list[HealthObservation]:
    if not caller.can(Permission.READ_OBSERVATIONS):
        raise HTTPException(status_code=403, detail="missing permission read:observations")
    allowed = visible_subjects(caller, _crews(repo))
    if allowed is not None and (subject_id is None or subject_id not in allowed):
        raise HTTPException(status_code=403, detail="subject_id is required and must be within scope")
    return repo.query(
        subject_id=subject_id,
        module=module,
        data_origin=data_origin,
        since=since,
        until=until,
        limit=limit,
    )


@router.post("/telemetry", response_model=TelemetryResponse, tags=["telemetry"])
def post_telemetry(
    body: TelemetryBatch,
    request: Request,
    repo: Repo,
    registry: Registry,
    caller: Caller,
) -> TelemetryResponse:
    """Wearable -> gateway. One result per event; rejected events are kept in the audit log."""
    authorize = write_authorizer(caller, repo)
    return ingest_telemetry(
        repo,
        registry,
        body.events,
        max_future_skew_seconds=request.app.state.settings.max_future_skew_seconds,
        authorize=authorize,
    )


@router.get("/telemetry/schema", tags=["telemetry"])
def telemetry_schema() -> dict:
    """JSON Schema of one ``TelemetryEvent`` (the 11-field contract plus optional provenance extensions)."""
    return TelemetryEvent.model_json_schema()


@router.get("/telemetry/rejections", response_model=list[RejectionOut], tags=["telemetry"])
def telemetry_rejections(
    repo: Repo, caller: Caller, limit: Annotated[int, Query(ge=1, le=1000)] = 100
) -> list[RejectionOut]:
    need(caller, Permission.READ_AUDIT)
    return [
        RejectionOut(
            rejection_id=r.rejection_id,
            received_at=r.received_at,
            source=r.source,
            device_id=r.device_id,
            reason=r.reason,
            payload=r.payload,
        )
        for r in repo.list_rejections(limit)
    ]


@router.get("/live", response_model=LiveResponse, tags=["telemetry"])
def live(repo: Repo, caller: Caller) -> LiveResponse:
    """Newest reading per device and indicator, for the dashboard (scoped to the caller)."""
    need(caller, Permission.READ_OBSERVATIONS)
    view = build_live(repo)
    allowed = visible_subjects(caller, crews(repo))
    if allowed is None:
        return view
    return view.model_copy(update={"devices": [d for d in view.devices if d.crew_id in allowed]})


@router.post("/sync/push", response_model=SyncPushResponse, tags=["sync"])
def sync_push(body: SyncPushRequest, repo: Repo, registry: Registry, caller: Caller) -> SyncPushResponse:
    need(caller, Permission.SYNC)
    authorize = write_authorizer(caller, repo)
    results = [
        ingest_observation(
            repo,
            registry,
            m.observation,
            mutation_id=m.mutation_id,
            channel="sync",
            audit_context={"client_id": body.client_id},
            authorize=authorize,
        )
        for m in body.mutations
    ]
    return SyncPushResponse(results=results, server_cursor=repo.head_seq())


@router.get("/sync/pull", response_model=SyncPullResponse, tags=["sync"])
def sync_pull(
    repo: Repo,
    caller: Caller,
    cursor: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=MAX_PULL_LIMIT)] = 500,
    subject_id: SubjectId | None = None,
) -> SyncPullResponse:
    need(caller, Permission.SYNC)
    need_subject_filter(caller, repo, subject_id)
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


# --------------------------------------------------------------------------- measurement schedules


def _mission(launch_at: datetime, return_at: datetime) -> MissionWindow:
    try:
        return MissionWindow(launch_at=launch_at, return_at=return_at)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _schedule_or_404(schedules: ScheduleRepository, schedule_id: UUID) -> MeasurementSchedule:
    schedule = schedules.get_schedule(schedule_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    return schedule


@router.post("/schedules", response_model=ScheduleWriteResult, tags=["schedules"])
def post_schedule(
    body: MeasurementSchedule, schedules: Schedules, registry: Registry, caller: Caller, repo: Repo
) -> ScheduleWriteResult:
    need(caller, Permission.WRITE_RECORDS)
    need_subject(caller, repo, body.subject_id)
    """Store a measurement plan (immutable; revise with ``supersedes``). Rejections are reported."""
    return store_schedule(schedules, registry, body)


@router.get("/schedules", response_model=list[MeasurementSchedule], tags=["schedules"])
def list_schedules(
    schedules: Schedules,
    caller: Caller,
    repo: Repo,
    subject_id: SubjectId | None = None,
    metric: str | None = None,
    current_only: bool = False,
) -> list[MeasurementSchedule]:
    need(caller, Permission.READ_RECORDS)
    need_subject_filter(caller, repo, subject_id)
    return schedules.list_schedules(subject_id=subject_id, metric=metric, current_only=current_only)


@router.get("/schedules/{schedule_id}", response_model=MeasurementSchedule, tags=["schedules"])
def read_schedule(schedule_id: UUID, schedules: Schedules, caller: Caller, repo: Repo) -> MeasurementSchedule:
    need(caller, Permission.READ_RECORDS)
    schedule = _schedule_or_404(schedules, schedule_id)
    need_subject(caller, repo, schedule.subject_id)
    return schedule


@router.get("/schedules/{schedule_id}/resolve", response_model=list[ResolvedEvent], tags=["schedules"])
def resolve(
    schedule_id: UUID,
    schedules: Schedules,
    launch_at: datetime,
    return_at: datetime,
    caller: Caller,
    repo: Repo,
) -> list[ResolvedEvent]:
    """Planned times for a mission. Resolved times are modeled (anchor + offset), not observations."""
    need(caller, Permission.READ_RECORDS)
    schedule = _schedule_or_404(schedules, schedule_id)
    need_subject(caller, repo, schedule.subject_id)
    try:
        return resolve_schedule(schedule, _mission(launch_at, return_at))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/schedules/{schedule_id}/coverage", response_model=ScheduleCoverage, tags=["schedules"])
def coverage(
    schedule_id: UUID,
    schedules: Schedules,
    repo: Repo,
    launch_at: datetime,
    return_at: datetime,
    caller: Caller,
) -> ScheduleCoverage:
    """Which planned windows contain observations, per data origin. Nothing is imputed."""
    need(caller, Permission.READ_RECORDS)
    schedule = _schedule_or_404(schedules, schedule_id)
    need_subject(caller, repo, schedule.subject_id)
    try:
        resolved = resolve_schedule(schedule, _mission(launch_at, return_at))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    observations = repo.query(subject_id=schedule.subject_id, module=schedule.module, limit=100_000)
    return schedule_coverage(schedule, resolved, observations)
