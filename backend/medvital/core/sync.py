"""Offline synchronisation wire contract (see docs/ARCHITECTURE.md §5).

Model: clients keep a local IndexedDB store plus an *outbox* of unsent observations.
Because observations are immutable and carry client-generated UUIDs, ``push`` is
idempotent and ``pull`` is a cursor over a server-assigned monotonic sequence. There is
no last-writer-wins merge — conflicts are only ever "same id, different content".
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from medvital.core.schema import HealthObservation

MAX_PUSH_BATCH = 500
MAX_PULL_LIMIT = 1000

ClientId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")]


class SyncMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mutation_id: UUID = Field(description="Client-generated; echoed back in results.")
    observation: HealthObservation


class SyncPushRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: ClientId
    mutations: list[SyncMutation] = Field(max_length=MAX_PUSH_BATCH)


class MutationStatus(StrEnum):
    ACCEPTED = "accepted"  # newly stored
    DUPLICATE = "duplicate"  # already stored with identical content (safe retry)
    REJECTED = "rejected"  # semantically invalid or conflicting; will never succeed unchanged


class MutationResult(BaseModel):
    mutation_id: UUID | None = None
    observation_id: UUID
    status: MutationStatus
    server_seq: int | None = None
    error: str | None = None


class SyncPushResponse(BaseModel):
    results: list[MutationResult]
    server_cursor: int = Field(description="Highest server_seq currently stored.")


class ServerChange(BaseModel):
    server_seq: int
    observation: HealthObservation


class SyncPullResponse(BaseModel):
    changes: list[ServerChange]
    next_cursor: int = Field(description="Pass as ?cursor= on the next pull.")
    has_more: bool
