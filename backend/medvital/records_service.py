"""Write/read paths for non-observation records (one place, so rules cannot diverge).

Every write returns a ``RecordWriteResult`` (accepted / duplicate / rejected with reason); nothing
is silently dropped. Storage is the generic append-only document store (D-028).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel

from medvital.core.records import (
    ALLOWED_TRANSITIONS,
    AIExplanation,
    CommandStatus,
    CommandStatusEvent,
    DeviceAssignment,
    EnvironmentalEvent,
    HumanIssuer,
    Mission,
    ReturnNowCommand,
    RuleFinding,
    SourceArtifact,
)
from medvital.core.reference import PublishedReference
from medvital.core.schema import DataOrigin
from medvital.db.repository import AddStatus, DocumentRepository, ObservationRepository

# Document kinds (stable storage keys).
K_MISSION = "mission"
K_ENV = "environmental_event"
K_ARTIFACT = "source_artifact"
K_COMMAND = "command"
K_COMMAND_EVENT = "command_event"
K_FINDING = "rule_finding"
K_AI = "ai_explanation"
K_REFERENCE = "reference"
K_DEVICE = "device_assignment"

# Measured observations may be cited by an AI explanation only when they come from a public source
# (D-022). Prefixes of public NASA/open-science sources verified in docs/NASA_SOURCES.md.
PUBLIC_SOURCE_PREFIXES = (
    "https://osdr.nasa.gov/",
    "https://api.nasa.gov/",
    "https://ccmc.gsfc.nasa.gov/",
    "https://pds-ppi.igpp.ucla.edu/",
    "https://pds.nasa.gov/",
)


class RecordWriteResult(BaseModel):
    record_id: str
    status: Literal["accepted", "duplicate", "rejected"]
    error: str | None = None


def _store(
    repo: DocumentRepository,
    kind: str,
    key: str,
    doc: BaseModel,
    *,
    tag: str | None = None,
    sort_time: datetime | None = None,
) -> RecordWriteResult:
    outcome = repo.add_document(kind, key, doc, tag=tag, sort_time=sort_time)
    if outcome.status is AddStatus.CONFLICT:
        return RecordWriteResult(
            record_id=key,
            status="rejected",
            error=f"a {kind} with this id already exists with different content; records are immutable",
        )
    return RecordWriteResult(
        record_id=key, status="accepted" if outcome.status is AddStatus.INSERTED else "duplicate"
    )


def _rejected(key: str, error: str) -> RecordWriteResult:
    return RecordWriteResult(record_id=key, status="rejected", error=error)


# --------------------------------------------------------------------------- missions


def store_mission(repo: DocumentRepository, mission: Mission) -> RecordWriteResult:
    return _store(repo, K_MISSION, mission.mission_id, mission, sort_time=mission.launch_at)


def get_mission(repo: DocumentRepository, mission_id: str) -> Mission | None:
    return repo.get_document(K_MISSION, mission_id, Mission)


def list_missions(repo: DocumentRepository) -> list[Mission]:
    return repo.list_documents(K_MISSION, Mission, order_by_time=True)


def missions_for_subject(repo: DocumentRepository, subject_id: str) -> list[Mission]:
    return [m for m in list_missions(repo) if subject_id in m.crew]


# --------------------------------------------------------------------------- device ownership


def assign_device(repo: DocumentRepository, assignment: DeviceAssignment) -> RecordWriteResult:
    key = str(assignment.assignment_id)
    mission = get_mission(repo, assignment.mission_id)
    if mission is None:
        return _rejected(key, f"unknown mission {assignment.mission_id!r}")
    if assignment.subject_id is not None and assignment.subject_id not in mission.crew:
        return _rejected(
            key, f"subject {assignment.subject_id!r} is not in mission {assignment.mission_id} crew"
        )
    return _store(repo, K_DEVICE, key, assignment, tag=assignment.device_id, sort_time=assignment.assigned_at)


def device_assignments(repo: DocumentRepository, device_id: str | None = None) -> list[DeviceAssignment]:
    return repo.list_documents(K_DEVICE, DeviceAssignment, tag=device_id, order_by_time=True)


def device_owner(repo: DocumentRepository, device_id: str) -> str | None:
    """Current subject of ``device_id`` (latest assignment wins); None if never assigned or unassigned."""
    history = device_assignments(repo, device_id)
    return history[-1].subject_id if history else None


# --------------------------------------------------------------------------- references


def store_reference(
    repo: DocumentRepository, reference: PublishedReference, registry=None
) -> RecordWriteResult:
    if reference.metric is not None and registry is not None:
        definition = registry.metric_definition(reference.metric)
        if definition is None:
            return _rejected(reference.reference_id, f"unknown metric {reference.metric!r}")
        if reference.unit != definition.unit:
            return _rejected(
                reference.reference_id,
                f"unit {reference.unit!r} differs from {reference.metric} canonical unit {definition.unit!r}",
            )
    if (
        reference.supersedes is not None
        and repo.get_document(K_REFERENCE, reference.supersedes, PublishedReference) is None
    ):
        return _rejected(reference.reference_id, "supersedes refers to an unknown reference")
    return _store(repo, K_REFERENCE, reference.reference_id, reference, tag=reference.metric)


# --------------------------------------------------------------------------- environment and artifacts


def store_environmental_event(repo: DocumentRepository, event: EnvironmentalEvent) -> RecordWriteResult:
    expected = EnvironmentalEvent.make_id(event.source_system, event.source_event_id, event.source_version)
    if event.event_id != expected:
        return _rejected(
            str(event.event_id), "event_id must be derived from (source_system, source_event_id, version)"
        )
    if (
        event.source_artifact_id is not None
        and repo.get_document(K_ARTIFACT, str(event.source_artifact_id), SourceArtifact) is None
    ):
        return _rejected(str(event.event_id), "source_artifact_id refers to an unknown artifact")
    return _store(repo, K_ENV, str(event.event_id), event, tag=event.event_type, sort_time=event.start_time)


def environmental_timeline(
    repo: DocumentRepository,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    event_type: str | None = None,
) -> list[EnvironmentalEvent]:
    """Events in time order (historical replay). Never associated with a subject's dose."""
    return repo.list_documents(
        K_ENV, EnvironmentalEvent, tag=event_type, since=since, until=until, order_by_time=True
    )


def store_artifact(repo: DocumentRepository, artifact: SourceArtifact) -> RecordWriteResult:
    if artifact.artifact_id != SourceArtifact.make_id(artifact.source_url, artifact.sha256):
        return _rejected(str(artifact.artifact_id), "artifact_id must be derived from (source_url, sha256)")
    return _store(
        repo,
        K_ARTIFACT,
        str(artifact.artifact_id),
        artifact,
        tag=artifact.dataset_id,
        sort_time=artifact.retrieved_at,
    )


def list_artifacts(repo: DocumentRepository, dataset_id: str | None = None) -> list[SourceArtifact]:
    return repo.list_documents(K_ARTIFACT, SourceArtifact, tag=dataset_id, order_by_time=True)


# --------------------------------------------------------------------------- RETURN_NOW (human-issued only)


class CommandState(BaseModel):
    command: ReturnNowCommand
    status: CommandStatus
    history: list[CommandStatusEvent]


def issue_return_now(repo: DocumentRepository, command: ReturnNowCommand) -> RecordWriteResult:
    """Store a human-issued RETURN_NOW. There is no automated caller of this function."""
    key = str(command.command_id)
    if command.issuer.issuer_type != "human":  # defensive; the model already forbids anything else
        return _rejected(key, "RETURN_NOW must be issued by a human")
    mission = get_mission(repo, command.mission_id)
    if mission is None:
        return _rejected(key, f"unknown mission {command.mission_id!r}")
    outside = sorted(set(command.subject_ids) - set(mission.crew))
    if outside:
        return _rejected(key, f"subjects not in mission crew: {', '.join(outside)}")
    result = _store(repo, K_COMMAND, key, command, tag=command.mission_id, sort_time=command.issued_at)
    if result.status == "accepted":
        initial = CommandStatusEvent(
            event_id=uuid4(),
            command_id=command.command_id,
            status=CommandStatus.ISSUED,
            actor=command.issuer,
            at=command.issued_at,
            note="issued",
        )
        _store(repo, K_COMMAND_EVENT, str(initial.event_id), initial, tag=key, sort_time=initial.at)
    return result


def command_state(repo: DocumentRepository, command_id: UUID) -> CommandState | None:
    command = repo.get_document(K_COMMAND, str(command_id), ReturnNowCommand)
    if command is None:
        return None
    history = repo.list_documents(
        K_COMMAND_EVENT, CommandStatusEvent, tag=str(command_id), order_by_time=True
    )
    return CommandState(
        command=command, status=history[-1].status if history else CommandStatus.ISSUED, history=history
    )


def transition_command(
    repo: DocumentRepository,
    command_id: UUID,
    status: CommandStatus,
    actor: HumanIssuer,
    at: datetime,
    note: str | None,
) -> RecordWriteResult:
    state = command_state(repo, command_id)
    key = str(command_id)
    if state is None:
        return _rejected(key, "unknown command")
    if status not in ALLOWED_TRANSITIONS[state.status]:
        return _rejected(key, f"transition {state.status.value} -> {status.value} is not allowed")
    if at < state.history[-1].at:
        return _rejected(key, "status time precedes the previous status")
    event = CommandStatusEvent(
        event_id=uuid4(), command_id=command_id, status=status, actor=actor, at=at, note=note
    )
    result = _store(repo, K_COMMAND_EVENT, str(event.event_id), event, tag=key, sort_time=at)
    return RecordWriteResult(record_id=key, status=result.status, error=result.error)


def list_commands(repo: DocumentRepository, mission_id: str | None = None) -> list[ReturnNowCommand]:
    return repo.list_documents(K_COMMAND, ReturnNowCommand, tag=mission_id, order_by_time=True)


# --------------------------------------------------------------------------- rule findings


def store_finding(repo: DocumentRepository, finding: RuleFinding) -> RecordWriteResult:
    return _store(
        repo,
        K_FINDING,
        str(finding.finding_id),
        finding,
        tag=finding.category.value,
        sort_time=finding.evaluated_at,
    )


def list_findings(
    repo: DocumentRepository, *, category: str | None = None, since: datetime | None = None
) -> list[RuleFinding]:
    return repo.list_documents(K_FINDING, RuleFinding, tag=category, since=since, order_by_time=True)


# --------------------------------------------------------------------------- AI explanations


def store_ai_explanation(
    repo: DocumentRepository, observations: ObservationRepository, explanation: AIExplanation
) -> RecordWriteResult:
    """Enforce D-022: cited records must exist, and measured data must come from a public source."""
    key = str(explanation.explanation_id)
    for oid in explanation.cited_observation_ids:
        stored = observations.get(oid)
        if stored is None:
            return _rejected(key, f"cited observation {oid} does not exist")
        prov = stored.observation.provenance
        if prov.data_origin is DataOrigin.MEASURED and not (prov.source_ref or "").startswith(
            PUBLIC_SOURCE_PREFIXES
        ):
            return _rejected(
                key, f"cited observation {oid} is measured data without a public NASA source (D-022)"
            )
    for fid in explanation.cited_finding_ids:
        if repo.get_document(K_FINDING, str(fid), RuleFinding) is None:
            return _rejected(key, f"cited finding {fid} does not exist")
    return _store(repo, K_AI, key, explanation, tag=explanation.provider, sort_time=explanation.created_at)


def list_ai_explanations(repo: DocumentRepository) -> list[AIExplanation]:
    return repo.list_documents(K_AI, AIExplanation, order_by_time=True)


# --------------------------------------------------------------------------- replication between stations


def replicate_command_event(repo: DocumentRepository, event: CommandStatusEvent) -> RecordWriteResult:
    """Accept a status event created at another station: its command must exist here first."""
    key = str(event.event_id)
    if repo.get_document(K_COMMAND, str(event.command_id), ReturnNowCommand) is None:
        return _rejected(key, "command not present yet; retry after the command has been replicated")
    if event.actor.issuer_type != "human":
        return _rejected(key, "command status changes must be made by a human")
    return _store(repo, K_COMMAND_EVENT, key, event, tag=str(event.command_id), sort_time=event.at)


REPLICABLE_KINDS = (
    K_DEVICE,
    K_MISSION,
    K_REFERENCE,
    K_ARTIFACT,
    K_ENV,
    K_COMMAND,
    K_COMMAND_EVENT,
    K_FINDING,
    K_AI,
)


def replicate(
    repo: DocumentRepository, observations: ObservationRepository, kind: str, payload: dict, registry=None
) -> RecordWriteResult:
    """Store a record received from another station through the same validation as a local write."""
    try:
        if kind == K_MISSION:
            return store_mission(repo, Mission.model_validate(payload))
        if kind == K_DEVICE:
            return assign_device(repo, DeviceAssignment.model_validate(payload))
        if kind == K_REFERENCE:
            return store_reference(repo, PublishedReference.model_validate(payload), registry)
        if kind == K_ARTIFACT:
            return store_artifact(repo, SourceArtifact.model_validate(payload))
        if kind == K_ENV:
            return store_environmental_event(repo, EnvironmentalEvent.model_validate(payload))
        if kind == K_COMMAND:
            command = ReturnNowCommand.model_validate(payload)
            # Replicated commands keep their original status history; do not create a second "issued" event.
            if get_mission(repo, command.mission_id) is None:
                return _rejected(str(command.command_id), "mission not present yet; replicate missions first")
            return _store(
                repo,
                K_COMMAND,
                str(command.command_id),
                command,
                tag=command.mission_id,
                sort_time=command.issued_at,
            )
        if kind == K_COMMAND_EVENT:
            return replicate_command_event(repo, CommandStatusEvent.model_validate(payload))
        if kind == K_FINDING:
            return store_finding(repo, RuleFinding.model_validate(payload))
        if kind == K_AI:
            return store_ai_explanation(repo, observations, AIExplanation.model_validate(payload))
    except ValueError as exc:  # pydantic ValidationError is a ValueError
        return _rejected(str(payload.get("id", "?"))[:64], f"invalid {kind}: {str(exc)[:300]}")
    return _rejected("?", f"kind {kind!r} is not replicable")
