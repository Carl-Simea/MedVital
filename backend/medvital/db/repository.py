"""Observation repository protocol and the in-memory implementation.

Contract (both implementations must honour it; ``tests/test_repository.py`` is written
against the protocol):

* append-only: ``add`` never updates an existing row;
* idempotent: re-adding an identical observation returns DUPLICATE with the original seq;
* conflict-safe: same id but different content returns CONFLICT and stores nothing;
* ``server_seq`` is assigned by the store, strictly increasing, gap-tolerant.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel

from medvital.core.reference import PublishedReference, Verification
from medvital.core.schedule import MeasurementSchedule, schedule_fingerprint
from medvital.core.schema import DataOrigin, HealthObservation, ModuleId, observation_fingerprint

M = TypeVar("M", bound=BaseModel)


def document_fingerprint(doc: BaseModel) -> str:
    """Content hash of an immutable document (canonical JSON of the *current* model)."""
    canonical = json.dumps(doc.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


@dataclass(frozen=True)
class WriteAuditRecord:
    """Who/what wrote an *accepted* observation (rejections live in the rejection log)."""

    audit_id: int
    server_seq: int
    observation_id: UUID
    channel: str  # api | sync | telemetry | simulation
    client_id: str | None
    device_id: str | None
    recorded_at: datetime


class DocumentRepository(Protocol):
    """Generic append-only store for immutable records (missions, environmental events, source
    artifacts, commands and their status events, rule findings, AI explanations, references).

    Same contract as observations: append-only, idempotent by (kind, key) + content, conflict-safe.
    ``tag`` and ``sort_time`` are indexed filters chosen by each record type.
    """

    def add_document(
        self,
        kind: str,
        key: str,
        doc: BaseModel,
        *,
        tag: str | None = None,
        sort_time: datetime | None = None,
    ) -> AddOutcome: ...

    def get_document(self, kind: str, key: str, model: type[M]) -> M | None: ...

    def list_documents(
        self,
        kind: str,
        model: type[M],
        *,
        tag: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        order_by_time: bool = False,
        limit: int = 10_000,
    ) -> list[M]: ...


@dataclass(frozen=True)
class DocumentChange:
    seq: int
    kind: str
    key: str
    payload: dict[str, Any]


class DocumentFeed(Protocol):
    def document_changes_since(self, cursor: int, *, limit: int = 500) -> list[DocumentChange]: ...

    def document_head_seq(self) -> int: ...


class WriteAuditRepository(Protocol):
    def record_write(
        self,
        *,
        server_seq: int,
        observation_id: UUID,
        channel: str,
        client_id: str | None,
        device_id: str | None,
    ) -> None: ...

    def list_writes(self, limit: int = 100) -> list[WriteAuditRecord]: ...


class ReferenceRepository(Protocol):
    """Published references (D-019): immutable, idempotent by reference_id + content."""

    def add_reference(self, reference: PublishedReference) -> AddOutcome: ...

    def get_reference(self, reference_id: str) -> PublishedReference | None: ...

    def list_references(
        self, *, metric: str | None = None, verification: Verification | None = None
    ) -> list[PublishedReference]: ...


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

    def record_write(
        self,
        *,
        server_seq: int,
        observation_id: UUID,
        channel: str,
        client_id: str | None,
        device_id: str | None,
    ) -> None: ...


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
        # Generic immutable documents: kind -> key -> (document, fingerprint, seq).
        self._docs: dict[str, dict[str, tuple[Any, str, int, str | None, datetime | None]]] = {}
        self._doc_seq = 0
        self._write_audit: list[WriteAuditRecord] = []

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

    # ----------------------------------------------------------------- immutable documents

    def add_document(
        self,
        kind: str,
        key: str,
        doc: BaseModel,
        *,
        tag: str | None = None,
        sort_time: datetime | None = None,
    ) -> AddOutcome:
        fingerprint = document_fingerprint(doc)
        with self._lock:
            table = self._docs.setdefault(kind, {})
            if key in table:
                _, stored_fp, seq, _, _ = table[key]
                status = AddStatus.DUPLICATE if stored_fp == fingerprint else AddStatus.CONFLICT
                return AddOutcome(status, seq)
            self._doc_seq += 1
            table[key] = (doc, fingerprint, self._doc_seq, tag, sort_time)
            return AddOutcome(AddStatus.INSERTED, self._doc_seq)

    def get_document(self, kind: str, key: str, model: type[M]) -> M | None:
        with self._lock:
            entry = self._docs.get(kind, {}).get(key)
        return entry[0] if entry else None

    def list_documents(
        self,
        kind: str,
        model: type[M],
        *,
        tag: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        order_by_time: bool = False,
        limit: int = 10_000,
    ) -> list[M]:
        with self._lock:
            entries = list(self._docs.get(kind, {}).values())
        out = [
            e
            for e in entries
            if (tag is None or e[3] == tag)
            and (since is None or (e[4] is not None and e[4] >= since))
            and (until is None or (e[4] is not None and e[4] < until))
        ]
        if order_by_time:
            out.sort(key=lambda e: (e[4] is None, e[4] or datetime.min.replace(tzinfo=UTC), e[2]))
        else:
            out.sort(key=lambda e: e[2])
        return [e[0] for e in out[:limit]]

    def add_reference(self, reference: PublishedReference) -> AddOutcome:
        return self.add_document("reference", reference.reference_id, reference, tag=reference.metric)

    def get_reference(self, reference_id: str) -> PublishedReference | None:
        return self.get_document("reference", reference_id, PublishedReference)

    def list_references(
        self, *, metric: str | None = None, verification: Verification | None = None
    ) -> list[PublishedReference]:
        rows = self.list_documents("reference", PublishedReference, tag=metric)
        return [r for r in rows if verification is None or r.verification is verification]

    def document_changes_since(self, cursor: int, *, limit: int = 500) -> list[DocumentChange]:
        with self._lock:
            entries = [
                (seq, kind, key, doc)
                for kind, table in self._docs.items()
                for key, (doc, _, seq, _, _) in table.items()
            ]
        entries.sort(key=lambda e: e[0])
        return [
            DocumentChange(seq=s, kind=k, key=key, payload=d.model_dump(mode="json"))
            for s, k, key, d in entries
            if s > cursor
        ][:limit]

    def document_head_seq(self) -> int:
        with self._lock:
            return self._doc_seq

    # ----------------------------------------------------------------- accepted-write audit

    def record_write(
        self,
        *,
        server_seq: int,
        observation_id: UUID,
        channel: str,
        client_id: str | None,
        device_id: str | None,
    ) -> None:
        with self._lock:
            self._write_audit.append(
                WriteAuditRecord(
                    audit_id=len(self._write_audit) + 1,
                    server_seq=server_seq,
                    observation_id=observation_id,
                    channel=channel,
                    client_id=client_id,
                    device_id=device_id,
                    recorded_at=datetime.now(UTC),
                )
            )

    def list_writes(self, limit: int = 100) -> list[WriteAuditRecord]:
        with self._lock:
            return list(reversed(self._write_audit))[:limit]
