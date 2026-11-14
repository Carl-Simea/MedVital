"""Observation repository protocol and the in-memory implementation.

Contract (both implementations must honour it; ``tests/test_repository.py`` is written
against the protocol):

* append-only: ``add`` never updates an existing row;
* idempotent: re-adding an identical observation returns DUPLICATE with the original seq;
* conflict-safe: same id but different content returns CONFLICT and stores nothing;
* ``server_seq`` is assigned by the store, strictly increasing, gap-tolerant.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from medvital.core.schedule import MeasurementSchedule, schedule_fingerprint
from medvital.core.schema import DataOrigin, HealthObservation, ModuleId, observation_fingerprint


class AddStatus(StrEnum):
    INSERTED = "inserted"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class AddOutcome:
    status: AddStatus
    server_seq: int | None


@dataclass(frozen=True)
class StoredObservation:
    server_seq: int
    received_at: datetime
    observation: HealthObservation


@dataclass(frozen=True)
class RejectedRecord:
    """Audit entry for a payload the gateway refused. Rejections are kept, never dropped."""

    rejection_id: int
    received_at: datetime
    source: str  # e.g. "telemetry"
    device_id: str | None
    reason: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class UpstreamFailure:
    """An observation an upstream station refused. Kept for audit; never retried automatically."""

    failure_id: int
    destination: str
    observation_id: UUID
    server_seq: int
    error: str
    recorded_at: datetime


class UpstreamStateRepository(Protocol):
    """Per-destination delivery cursor over the local ``server_seq`` plus a refusal audit log."""

    def upstream_cursor(self, destination: str) -> int: ...

    def set_upstream_cursor(self, destination: str, server_seq: int) -> None:
        """Monotonic: moving a cursor backwards raises ValueError."""
        ...

    def record_upstream_failure(
        self, destination: str, observation_id: UUID, server_seq: int, error: str
    ) -> None: ...

    def list_upstream_failures(
        self, destination: str | None = None, limit: int = 100
    ) -> list[UpstreamFailure]: ...


class ObservationRepository(Protocol):
    def add(self, observation: HealthObservation) -> AddOutcome: ...

    def latest_by_device_metric(self) -> list[HealthObservation]:
        """Newest observation (by observed_at) for every (device, subject, metric) series."""
        ...

    def record_rejection(
        self, *, source: str, device_id: str | None, reason: str, payload: dict[str, Any]
    ) -> None: ...

    def rejection_count(self) -> int: ...

    def list_rejections(self, limit: int = 100) -> list[RejectedRecord]: ...

    def get(self, observation_id: UUID) -> StoredObservation | None: ...

    def query(
        self,
        *,
        subject_id: str | None = None,
        module: ModuleId | None = None,
        data_origin: DataOrigin | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 1000,
    ) -> list[HealthObservation]: ...

    def changes_since(
        self, cursor: int, *, limit: int = 500, subject_id: str | None = None
    ) -> list[StoredObservation]: ...

    def head_seq(self) -> int: ...


class ScheduleRepository(Protocol):
    """Measurement schedules: same append-only / idempotent / conflict-safe contract as observations."""

    def add_schedule(self, schedule: MeasurementSchedule) -> AddOutcome: ...

    def get_schedule(self, schedule_id: UUID) -> MeasurementSchedule | None: ...

    def list_schedules(
        self, *, subject_id: str | None = None, metric: str | None = None, current_only: bool = False
    ) -> list[MeasurementSchedule]:
        """In insertion order. ``current_only`` drops schedules superseded by another stored one."""
        ...


def filter_schedules(
    rows: list[MeasurementSchedule], subject_id: str | None, metric: str | None, current_only: bool
) -> list[MeasurementSchedule]:
    superseded = {s.supersedes for s in rows if s.supersedes is not None} if current_only else set()
    return [
        s
        for s in rows
        if (subject_id is None or s.subject_id == subject_id)
        and (metric is None or s.metric == metric)
        and s.id not in superseded
    ]


class InMemoryObservationRepository:
    """Process-local store. Thread-safe; data is lost on restart (development/tests)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: list[StoredObservation] = []
        self._by_id: dict[UUID, tuple[StoredObservation, str]] = {}
        self._rejections: list[RejectedRecord] = []
        self._schedules: list[MeasurementSchedule] = []
        self._schedule_index: dict[UUID, tuple[int, str]] = {}  # id -> (seq, fingerprint)
        self._upstream_cursors: dict[str, int] = {}
        self._upstream_failures: list[UpstreamFailure] = []

    def add(self, observation: HealthObservation) -> AddOutcome:
        fingerprint = observation_fingerprint(observation)
        with self._lock:
            existing = self._by_id.get(observation.id)
            if existing is not None:
                stored, stored_fp = existing
                status = AddStatus.DUPLICATE if stored_fp == fingerprint else AddStatus.CONFLICT
                return AddOutcome(status, stored.server_seq)
            row = StoredObservation(
                server_seq=len(self._rows) + 1,
                received_at=datetime.now(UTC),
                observation=observation,
            )
            self._rows.append(row)
            self._by_id[observation.id] = (row, fingerprint)
            return AddOutcome(AddStatus.INSERTED, row.server_seq)

    def get(self, observation_id: UUID) -> StoredObservation | None:
        with self._lock:
            entry = self._by_id.get(observation_id)
        return entry[0] if entry else None

    def query(
        self,
        *,
        subject_id: str | None = None,
        module: ModuleId | None = None,
        data_origin: DataOrigin | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 1000,
    ) -> list[HealthObservation]:
        with self._lock:
            rows = list(self._rows)
        out = []
        for row in rows:
            o = row.observation
            if subject_id is not None and o.subject_id != subject_id:
                continue
            if module is not None and o.module is not module:
                continue
            if data_origin is not None and o.provenance.data_origin is not data_origin:
                continue
            if since is not None and o.observed_at < since:
                continue
            if until is not None and o.observed_at >= until:
                continue
            out.append(o)
        out.sort(key=lambda o: (o.observed_at, str(o.id)))
        return out[:limit]

    def changes_since(
        self, cursor: int, *, limit: int = 500, subject_id: str | None = None
    ) -> list[StoredObservation]:
        with self._lock:
            rows = self._rows[max(cursor, 0) :]
        if subject_id is not None:
            rows = [r for r in rows if r.observation.subject_id == subject_id]
        return rows[:limit]

    def head_seq(self) -> int:
        with self._lock:
            return len(self._rows)

    def latest_by_device_metric(self) -> list[HealthObservation]:
        with self._lock:
            rows = list(self._rows)
        newest: dict[tuple[str, str, str], HealthObservation] = {}
        for row in rows:
            o = row.observation
            key = (o.device_id or "", o.subject_id, o.metric)
            current = newest.get(key)
            if current is None or o.observed_at >= current.observed_at:
                newest[key] = o
        return sorted(newest.values(), key=lambda o: (o.device_id or "", o.subject_id, o.metric))

    def record_rejection(
        self, *, source: str, device_id: str | None, reason: str, payload: dict[str, Any]
    ) -> None:
        with self._lock:
            self._rejections.append(
                RejectedRecord(
                    rejection_id=len(self._rejections) + 1,
                    received_at=datetime.now(UTC),
                    source=source,
                    device_id=device_id,
                    reason=reason,
                    payload=payload,
                )
            )

    def rejection_count(self) -> int:
        with self._lock:
            return len(self._rejections)

    def list_rejections(self, limit: int = 100) -> list[RejectedRecord]:
        with self._lock:
            return list(reversed(self._rejections))[:limit]

    def add_schedule(self, schedule: MeasurementSchedule) -> AddOutcome:
        fingerprint = schedule_fingerprint(schedule)
        with self._lock:
            existing = self._schedule_index.get(schedule.id)
            if existing is not None:
                seq, stored_fp = existing
                status = AddStatus.DUPLICATE if stored_fp == fingerprint else AddStatus.CONFLICT
                return AddOutcome(status, seq)
            self._schedules.append(schedule)
            seq = len(self._schedules)
            self._schedule_index[schedule.id] = (seq, fingerprint)
            return AddOutcome(AddStatus.INSERTED, seq)

    def get_schedule(self, schedule_id: UUID) -> MeasurementSchedule | None:
        with self._lock:
            entry = self._schedule_index.get(schedule_id)
            return self._schedules[entry[0] - 1] if entry else None

    def list_schedules(
        self, *, subject_id: str | None = None, metric: str | None = None, current_only: bool = False
    ) -> list[MeasurementSchedule]:
        with self._lock:
            rows = list(self._schedules)
        return filter_schedules(rows, subject_id, metric, current_only)

    def upstream_cursor(self, destination: str) -> int:
        with self._lock:
            return self._upstream_cursors.get(destination, 0)

    def set_upstream_cursor(self, destination: str, server_seq: int) -> None:
        with self._lock:
            if server_seq < self._upstream_cursors.get(destination, 0):
                raise ValueError("upstream cursor cannot move backwards")
            self._upstream_cursors[destination] = server_seq

    def record_upstream_failure(
        self, destination: str, observation_id: UUID, server_seq: int, error: str
    ) -> None:
        with self._lock:
            self._upstream_failures.append(
                UpstreamFailure(
                    failure_id=len(self._upstream_failures) + 1,
                    destination=destination,
                    observation_id=observation_id,
                    server_seq=server_seq,
                    error=error,
                    recorded_at=datetime.now(UTC),
                )
            )

    def list_upstream_failures(
        self, destination: str | None = None, limit: int = 100
    ) -> list[UpstreamFailure]:
        with self._lock:
            rows = [f for f in self._upstream_failures if destination is None or f.destination == destination]
        return list(reversed(rows))[:limit]
