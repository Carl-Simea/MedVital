"""Observation repository contract and the in-memory implementation.

Observations are append-only and immutable. Re-sending an identical observation is a harmless
duplicate; re-using an id with different content is a conflict and is rejected.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from medvital.core.observation import HealthObservation, ModuleId
from medvital.core.provenance import DataOrigin


@dataclass
class AddResult:
    accepted: list[UUID] = field(default_factory=list)
    duplicates: list[UUID] = field(default_factory=list)
    conflicts: list[UUID] = field(default_factory=list)


@dataclass(frozen=True)
class ChangePage:
    observations: list[HealthObservation]
    next_cursor: int
    has_more: bool


class ObservationRepository(Protocol):
    def add_many(self, observations: Sequence[HealthObservation]) -> AddResult: ...

    def query(
        self,
        *,
        astronaut_id: str | None = None,
        module: ModuleId | None = None,
        metric: str | None = None,
        origin: DataOrigin | None = None,
        limit: int = 1000,
    ) -> list[HealthObservation]: ...

    def changes_since(self, cursor: int, limit: int) -> ChangePage: ...


class InMemoryObservationRepository:
    """Thread-safe, process-local repository. Default for development and tests."""

    def __init__(self) -> None:
        self._rows: list[HealthObservation] = []  # position + 1 is the server cursor
        self._index: dict[UUID, int] = {}
        self._lock = threading.Lock()

    def add_many(self, observations: Sequence[HealthObservation]) -> AddResult:
        result = AddResult()
        with self._lock:
            for obs in observations:
                position = self._index.get(obs.id)
                if position is None:
                    self._index[obs.id] = len(self._rows)
                    self._rows.append(obs)
                    result.accepted.append(obs.id)
                elif self._rows[position] == obs:
                    result.duplicates.append(obs.id)
                else:
                    result.conflicts.append(obs.id)
        return result

    def query(
        self,
        *,
        astronaut_id: str | None = None,
        module: ModuleId | None = None,
        metric: str | None = None,
        origin: DataOrigin | None = None,
        limit: int = 1000,
    ) -> list[HealthObservation]:
        with self._lock:
            rows = list(self._rows)
        matches = [
            o
            for o in rows
            if (astronaut_id is None or o.astronaut_id == astronaut_id)
            and (module is None or o.module is module)
            and (metric is None or o.metric == metric)
            and (origin is None or o.provenance.origin is origin)
        ]
        matches.sort(key=lambda o: (o.observed_at, str(o.id)))
        return matches[:limit]

    def changes_since(self, cursor: int, limit: int) -> ChangePage:
        if cursor < 0 or limit < 1:
            raise ValueError("cursor must be >= 0 and limit >= 1")
        with self._lock:
            page = self._rows[cursor : cursor + limit]
            next_cursor = cursor + len(page)
            return ChangePage(page, next_cursor, next_cursor < len(self._rows))
