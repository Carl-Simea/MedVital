"""API v1 routes for non-observation records, analysis, rules, commands and audit (backend M3).

Authorization (D-029) is resolved here, at the boundary: each route checks a permission and the
subject/mission scope, then passes plain filters to processing code.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from medvital.analysis import AnalysisConfig, AnalysisReport, analyze
from medvital.api.deps import get_principal, get_registry, get_repository
from medvital.api.guards import crews, need, need_mission, need_station, need_subject
from medvital.authz import (
    Permission,
    Principal,
    can_access_mission,
    may_issue_return_now,
    visible_subjects,
)
from medvital.core.module_spec import ModuleRegistry
from medvital.core.records import (
    AIExplanation,
    CommandStatus,
    DeviceAssignment,
    EnvironmentalEvent,
    HumanIssuer,
    Mission,
    ReturnNowCommand,
    RuleFinding,
    SourceArtifact,
)
from medvital.core.reference import PublishedReference, Verification
from medvital.core.schema import ModuleId, SubjectId
from medvital.records_service import (
    CommandState,
    RecordWriteResult,
    assign_device,
    command_state,
    device_assignments,
    environmental_timeline,
    get_mission,
    issue_return_now,
    list_ai_explanations,
    list_artifacts,
    list_commands,
    list_findings,
    list_missions,
    replicate,
    store_ai_explanation,
    store_environmental_event,
    store_finding,
    store_mission,
    store_reference,
    transition_command,
)
from medvital.rules import RuleConfig, evaluate

router = APIRouter(prefix="/api/v1")

Repo = Annotated[object, Depends(get_repository)]
Registry = Annotated[ModuleRegistry, Depends(get_registry)]
Caller = Annotated[Principal, Depends(get_principal)]


# --------------------------------------------------------------------------- missions


@router.post("/missions", response_model=RecordWriteResult, tags=["missions"])
def post_mission(body: Mission, repo: Repo, caller: Caller) -> RecordWriteResult:
    need(caller, Permission.WRITE_RECORDS)
    need_mission(caller, body.mission_id)  # cannot create (and so gain scope over) unassigned missions
    return store_mission(repo, body)


@router.get("/missions", response_model=list[Mission], tags=["missions"])
def get_missions(repo: Repo, caller: Caller) -> list[Mission]:
    need(caller, Permission.READ_RECORDS)
    return [m for m in list_missions(repo) if can_access_mission(caller, m.mission_id)]


@router.get("/missions/{mission_id}", response_model=Mission, tags=["missions"])
def get_one_mission(mission_id: str, repo: Repo, caller: Caller) -> Mission:
    need(caller, Permission.READ_RECORDS)
    need_mission(caller, mission_id)
    mission = get_mission(repo, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="mission not found")
    return mission


# --------------------------------------------------------------------------- references


@router.post("/references", response_model=RecordWriteResult, tags=["references"])
def post_reference(
    body: PublishedReference, repo: Repo, registry: Registry, caller: Caller
) -> RecordWriteResult:
    need(caller, Permission.WRITE_RECORDS)
    return store_reference(repo, body, registry)


@router.get("/references", response_model=list[PublishedReference], tags=["references"])
def get_references(
    repo: Repo, caller: Caller, metric: str | None = None, verification: Verification | None = None
) -> list[PublishedReference]:
    need(caller, Permission.READ_RECORDS)
    return repo.list_references(metric=metric, verification=verification)


@router.get("/references/{reference_id}", response_model=PublishedReference, tags=["references"])
def get_reference(reference_id: str, repo: Repo, caller: Caller) -> PublishedReference:
    need(caller, Permission.READ_RECORDS)
    ref = repo.get_reference(reference_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="reference not found")
    return ref


# --------------------------------------------------------------------------- environment and sources


@router.post("/environment/events", response_model=RecordWriteResult, tags=["environment"])
def post_environmental_event(body: EnvironmentalEvent, repo: Repo, caller: Caller) -> RecordWriteResult:
    need(caller, Permission.WRITE_RECORDS)
    return store_environmental_event(repo, body)


@router.get("/environment/events", response_model=list[EnvironmentalEvent], tags=["environment"])
def get_environmental_timeline(
    repo: Repo,
    caller: Caller,
    since: datetime | None = None,
    until: datetime | None = None,
    event_type: str | None = None,
) -> list[EnvironmentalEvent]:
    """Time-ordered environmental record (historical replay). Never a person's dose."""
    need(caller, Permission.READ_RECORDS)
    return environmental_timeline(repo, since=since, until=until, event_type=event_type)


@router.get("/sources/artifacts", response_model=list[SourceArtifact], tags=["environment"])
def get_artifacts(repo: Repo, caller: Caller, dataset_id: str | None = None) -> list[SourceArtifact]:
    need(caller, Permission.READ_RECORDS)
    return list_artifacts(repo, dataset_id)


# --------------------------------------------------------------------------- analysis


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_id: SubjectId
    module: ModuleId | None = None
    metric: str | None = None
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None
    config: AnalysisConfig = Field(default_factory=AnalysisConfig)


@router.post("/analysis", response_model=AnalysisReport, tags=["analysis"])
def run_analysis(body: AnalysisRequest, repo: Repo, registry: Registry, caller: Caller) -> AnalysisReport:
    """Descriptive statistics, own-baseline deviations, data quality and review flags for one subject."""
    need(caller, Permission.READ_ANALYSIS)
    need_subject(caller, repo, body.subject_id)
    observations = repo.query(
        subject_id=body.subject_id, module=body.module, since=body.since, until=body.until, limit=100_000
    )
    if body.metric is not None:
        observations = [o for o in observations if o.metric == body.metric]
    return analyze(observations, body.config, registry)


# --------------------------------------------------------------------------- rules


class RuleEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    now: AwareDatetime | None = None
    persist: bool = False
    config: RuleConfig = Field(default_factory=RuleConfig)


@router.post("/rules/evaluate", response_model=list[RuleFinding], tags=["rules"])
def evaluate_rules(
    body: RuleEvaluationRequest, repo: Repo, registry: Registry, caller: Caller
) -> list[RuleFinding]:
    """Non-clinical review flags (D-021). ``persist`` stores them (idempotent: same inputs, same ids)."""
    need(caller, Permission.EVALUATE_RULES)
    findings = evaluate(repo, registry, body.now or datetime.now(UTC), body.config)
    allowed = visible_subjects(caller, crews(repo))
    if allowed is not None:
        findings = [f for f in findings if f.subject_id is None or f.subject_id in allowed]
    if body.persist:
        for f in findings:
            store_finding(repo, f)
    return findings


@router.get("/rules/findings", response_model=list[RuleFinding], tags=["rules"])
def get_findings(
    repo: Repo, caller: Caller, category: str | None = None, since: datetime | None = None
) -> list[RuleFinding]:
    need(caller, Permission.READ_RECORDS)
    allowed = visible_subjects(caller, crews(repo))
    return [
        f
        for f in list_findings(repo, category=category, since=since)
        if allowed is None or f.subject_id is None or f.subject_id in allowed
    ]


# --------------------------------------------------------------------------- RETURN_NOW (human-issued only)


@router.post("/commands/return-now", response_model=RecordWriteResult, tags=["commands"])
def post_return_now(body: ReturnNowCommand, repo: Repo, caller: Caller) -> RecordWriteResult:
    """Record a RETURN_NOW issued by a human. MEDVITAL never computes or suggests this command."""
    if not may_issue_return_now(caller, body.mission_id, body.issuer.principal_id):
        raise HTTPException(
            status_code=403, detail="only an authorized human may issue RETURN_NOW in their own name"
        )
    return issue_return_now(repo, body)


class CommandTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CommandStatus
    actor: HumanIssuer
    at: AwareDatetime
    note: str | None = Field(default=None, max_length=2000)


@router.post("/commands/{command_id}/status", response_model=RecordWriteResult, tags=["commands"])
def post_command_status(
    command_id: UUID, body: CommandTransitionRequest, repo: Repo, caller: Caller
) -> RecordWriteResult:
    need(caller, Permission.UPDATE_COMMAND)
    state = command_state(repo, command_id)
    if state is None:
        raise HTTPException(status_code=404, detail="command not found")
    need_mission(caller, state.command.mission_id)
    if caller.human and caller.principal_id != body.actor.principal_id:
        raise HTTPException(status_code=403, detail="status changes must be made in the caller's own name")
    return transition_command(repo, command_id, body.status, body.actor, body.at, body.note)


@router.get("/commands", response_model=list[ReturnNowCommand], tags=["commands"])
def get_commands(repo: Repo, caller: Caller, mission_id: str | None = None) -> list[ReturnNowCommand]:
    need(caller, Permission.READ_COMMANDS)
    return [c for c in list_commands(repo, mission_id) if can_access_mission(caller, c.mission_id)]


@router.get("/commands/{command_id}", response_model=CommandState, tags=["commands"])
def get_command(command_id: UUID, repo: Repo, caller: Caller) -> CommandState:
    need(caller, Permission.READ_COMMANDS)
    state = command_state(repo, command_id)
    if state is None:
        raise HTTPException(status_code=404, detail="command not found")
    need_mission(caller, state.command.mission_id)
    return state


# --------------------------------------------------------------------------- AI explanations (Gemini, M7)


@router.post("/ai/explanations", response_model=RecordWriteResult, tags=["ai"])
def post_ai_explanation(body: AIExplanation, repo: Repo, caller: Caller) -> RecordWriteResult:
    """Store an explanation made elsewhere. Never an observation; citations must be permitted (D-022)."""
    need(caller, Permission.WRITE_AI_EXPLANATION)
    if caller.human and body.requested_by != caller.principal_id:
        raise HTTPException(status_code=403, detail="requested_by must be the caller")
    for oid in body.cited_observation_ids:
        stored = repo.get(oid)
        if stored is not None:
            need_subject(caller, repo, stored.observation.subject_id)
    return store_ai_explanation(repo, repo, body)


@router.get("/ai/explanations", response_model=list[AIExplanation], tags=["ai"])
def get_ai_explanations(repo: Repo, caller: Caller) -> list[AIExplanation]:
    need(caller, Permission.READ_RECORDS)
    return list_ai_explanations(repo)


# --------------------------------------------------------------------------- audit


class WriteAuditOut(BaseModel):
    audit_id: int
    server_seq: int
    observation_id: UUID
    channel: str
    client_id: str | None
    device_id: str | None
    recorded_at: datetime


class UpstreamFailureOut(BaseModel):
    failure_id: int
    destination: str
    observation_id: UUID
    server_seq: int
    error: str
    recorded_at: datetime


@router.get("/audit/writes", response_model=list[WriteAuditOut], tags=["audit"])
def get_write_audit(
    repo: Repo, caller: Caller, limit: Annotated[int, Query(ge=1, le=1000)] = 100
) -> list[WriteAuditOut]:
    need(caller, Permission.READ_AUDIT)
    return [WriteAuditOut(**w.__dict__) for w in repo.list_writes(limit)]


@router.get("/audit/upstream-failures", response_model=list[UpstreamFailureOut], tags=["audit"])
def get_upstream_failures(
    repo: Repo,
    caller: Caller,
    destination: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[UpstreamFailureOut]:
    need(caller, Permission.READ_AUDIT)
    return [UpstreamFailureOut(**f.__dict__) for f in repo.list_upstream_failures(destination, limit)]


# --------------------------------------------------------------------------- station-to-station record sync


class DocumentItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    document: dict


class DocumentPushRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
    documents: list[DocumentItem] = Field(max_length=500)


class DocumentChangeOut(BaseModel):
    seq: int
    kind: str
    key: str
    document: dict


class DocumentPullResponse(BaseModel):
    changes: list[DocumentChangeOut]
    next_cursor: int
    has_more: bool


@router.post("/sync/documents/push", response_model=list[RecordWriteResult], tags=["sync"])
def push_documents(
    body: DocumentPushRequest, repo: Repo, registry: Registry, caller: Caller
) -> list[RecordWriteResult]:
    """Replicate records from another station. Each goes through the same validation as a local write."""
    need_station(caller, "station-to-station record replication")
    return [replicate(repo, repo, item.kind, item.document, registry) for item in body.documents]


@router.get("/sync/documents/pull", response_model=DocumentPullResponse, tags=["sync"])
def pull_documents(
    repo: Repo,
    caller: Caller,
    cursor: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> DocumentPullResponse:
    need_station(caller, "station-to-station record replication")
    head = repo.document_head_seq()
    rows = repo.document_changes_since(cursor, limit=limit + 1)
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = page[-1].seq if has_more else max(head, page[-1].seq if page else 0, cursor)
    return DocumentPullResponse(
        changes=[DocumentChangeOut(seq=r.seq, kind=r.kind, key=r.key, document=r.payload) for r in page],
        next_cursor=next_cursor,
        has_more=has_more,
    )


# --------------------------------------------------------------------------- device ownership


@router.post("/devices/assignments", response_model=RecordWriteResult, tags=["devices"])
def post_device_assignment(body: DeviceAssignment, repo: Repo, caller: Caller) -> RecordWriteResult:
    """Assign a device to a crew member (operators/ground control in scope). Astronauts cannot."""
    need(caller, Permission.WRITE_RECORDS)
    need_mission(caller, body.mission_id)
    if caller.human and body.assigned_by != caller.principal_id:
        raise HTTPException(status_code=403, detail="assigned_by must be the caller")
    return assign_device(repo, body)


@router.get("/devices/assignments", response_model=list[DeviceAssignment], tags=["devices"])
def get_device_assignments(
    repo: Repo, caller: Caller, device_id: str | None = None
) -> list[DeviceAssignment]:
    need(caller, Permission.READ_RECORDS)
    return [a for a in device_assignments(repo, device_id) if can_access_mission(caller, a.mission_id)]
