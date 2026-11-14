"""Single write path for observations: semantic validation + idempotent append.

Used by both ``POST /observations`` and ``POST /sync/push`` so the rules cannot diverge.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from medvital.core.module_spec import ModuleRegistry, ObservationRejected
from medvital.core.schema import HealthObservation
from medvital.core.sync import MutationResult, MutationStatus
from medvital.db.repository import AddStatus, ObservationRepository


def ingest_observation(
    repo: ObservationRepository,
    registry: ModuleRegistry,
    observation: HealthObservation,
    mutation_id=None,
    *,
    channel: str = "api",
    audit_context: dict[str, Any] | None = None,
    authorize: Callable[[HealthObservation], str | None] | None = None,
) -> MutationResult:
    """Validate and append. Every rejection is also written to the rejection log (never silently
    dropped), tagged with ``channel`` ("api", "sync", "simulation") and ``audit_context``."""

    def rejected(error: str, server_seq: int | None = None) -> MutationResult:
        repo.record_rejection(
            source=channel,
            device_id=observation.device_id,
            reason=error,
            payload={
                **(audit_context or {}),
                **({"mutation_id": str(mutation_id)} if mutation_id is not None else {}),
                "observation": observation.model_dump(mode="json"),
            },
        )
        return MutationResult(
            mutation_id=mutation_id,
            observation_id=observation.id,
            status=MutationStatus.REJECTED,
            server_seq=server_seq,
            error=error,
        )

    if authorize is not None:
        problem = authorize(observation)
        if problem:
            return rejected(f"authorization: {problem}")
    try:
        registry.validate(observation)
    except ObservationRejected as exc:
        return rejected(str(exc))
    outcome = repo.add(observation)
    if outcome.status is AddStatus.CONFLICT:
        return rejected(
            "an observation with this id already exists with different content; "
            "observations are immutable — submit a correction with `supersedes`",
            outcome.server_seq,
        )
    if outcome.status is AddStatus.INSERTED:
        repo.record_write(
            server_seq=outcome.server_seq,
            observation_id=observation.id,
            channel=channel,
            client_id=(audit_context or {}).get("client_id"),
            device_id=observation.device_id,
        )
    status = MutationStatus.ACCEPTED if outcome.status is AddStatus.INSERTED else MutationStatus.DUPLICATE
    return MutationResult(
        mutation_id=mutation_id,
        observation_id=observation.id,
        status=status,
        server_seq=outcome.server_seq,
    )
