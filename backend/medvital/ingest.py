"""Single write path for observations: semantic validation + idempotent append.

Used by both ``POST /observations`` and ``POST /sync/push`` so the rules cannot diverge.
"""

from __future__ import annotations

from medvital.core.module_spec import ModuleRegistry, ObservationRejected
from medvital.core.schema import HealthObservation
from medvital.core.sync import MutationResult, MutationStatus
from medvital.db.repository import AddStatus, ObservationRepository


def ingest_observation(
    repo: ObservationRepository,
    registry: ModuleRegistry,
    observation: HealthObservation,
    mutation_id=None,
) -> MutationResult:
    try:
        registry.validate(observation)
    except ObservationRejected as exc:
        return MutationResult(
            mutation_id=mutation_id,
            observation_id=observation.id,
            status=MutationStatus.REJECTED,
            error=str(exc),
        )
    outcome = repo.add(observation)
    if outcome.status is AddStatus.CONFLICT:
        return MutationResult(
            mutation_id=mutation_id,
            observation_id=observation.id,
            status=MutationStatus.REJECTED,
            server_seq=outcome.server_seq,
            error="an observation with this id already exists with different content; "
            "observations are immutable — submit a correction with `supersedes`",
        )
    status = MutationStatus.ACCEPTED if outcome.status is AddStatus.INSERTED else MutationStatus.DUPLICATE
    return MutationResult(
        mutation_id=mutation_id,
        observation_id=observation.id,
        status=status,
        server_seq=outcome.server_seq,
    )
