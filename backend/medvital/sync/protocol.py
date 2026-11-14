"""Wire models for the offline sync protocol.

Push items are accepted as raw dicts so one malformed observation is rejected on its own and
never blocks the rest of an offline client's batch.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from medvital.core.observation import HealthObservation

MAX_PUSH_BATCH = 500


class RejectedItem(BaseModel):
    id: str | None
    reason: str


class SyncPushRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    observations: list[dict[str, Any]] = Field(max_length=MAX_PUSH_BATCH)


class SyncPushResponse(BaseModel):
    accepted: list[str]
    duplicates: list[str]
    rejected: list[RejectedItem]


class SyncPullResponse(BaseModel):
    observations: list[HealthObservation]
    next_cursor: int
    has_more: bool
