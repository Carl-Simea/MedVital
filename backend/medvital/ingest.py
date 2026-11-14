"""Validate and store raw observations (the single write path for client data)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from medvital.core.observation import HealthObservation
from medvital.db.repository import ObservationRepository
from medvital.registry import ObservationRejected, validate_observation
from medvital.sync.protocol import RejectedItem, SyncPushResponse


def _reason(exc: ValueError) -> str:
    if isinstance(exc, ValidationError):
        # Report location and message only; never echo submitted values.
        parts = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:3]]
        return "; ".join(parts)
    return str(exc)


def ingest(repo: ObservationRepository, raw_items: Sequence[Mapping[str, Any]]) -> SyncPushResponse:
    valid: list[HealthObservation] = []
    rejected: list[RejectedItem] = []
    for raw in raw_items:
        raw_id = raw.get("id") if isinstance(raw, Mapping) else None
        try:
            obs = HealthObservation.model_validate(raw)
            validate_observation(obs)
        except (ValidationError, ObservationRejected) as exc:
            rejected.append(RejectedItem(id=str(raw_id) if raw_id else None, reason=_reason(exc)))
        else:
            valid.append(obs)

    result = repo.add_many(valid)
    rejected.extend(
        RejectedItem(id=str(i), reason="id already exists with different content")
        for i in result.conflicts
    )
    return SyncPushResponse(
        accepted=[str(i) for i in result.accepted],
        duplicates=[str(i) for i in result.duplicates],
        rejected=rejected,
    )
