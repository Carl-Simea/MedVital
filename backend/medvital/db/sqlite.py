"""SQLite observation store — the gateway's durable *local* storage.

Uses only the standard library (no new dependency), runs on a Raspberry Pi, and survives
restarts and loss of connectivity. Same contract as the in-memory repository
(``tests/test_repository.py`` runs against both): append-only, idempotent, conflict-safe,
strictly increasing ``server_seq``.

Not a replacement for the PostgreSQL design (docs/ARCHITECTURE.md §6): SQLite is the
spacecraft-side store; PostgreSQL remains the intended ground/cloud store.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from medvital.core.reference import PublishedReference, Verification
from medvital.core.schedule import MeasurementSchedule, schedule_fingerprint
from medvital.core.schema import DataOrigin, HealthObservation, ModuleId, observation_fingerprint
from medvital.db.repository import (
    AddOutcome,
    AddStatus,
    DocumentChange,
    M,
    RejectedRecord,
    StoredObservation,
    UpstreamFailure,
    WriteAuditRecord,
    document_fingerprint,
    filter_schedules,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    server_seq   INTEGER PRIMARY KEY AUTOINCREMENT,
    id           TEXT NOT NULL UNIQUE,
    fingerprint  TEXT NOT NULL,
    subject_id   TEXT NOT NULL,
    module       TEXT NOT NULL,
    metric       TEXT NOT NULL,
    device_id    TEXT,
    data_origin  TEXT NOT NULL,
    observed_at  TEXT NOT NULL,
    received_at  TEXT NOT NULL,
    payload      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS obs_subject_module_time ON observations (subject_id, module, observed_at);
CREATE INDEX IF NOT EXISTS obs_series ON observations (device_id, subject_id, metric, observed_at);

CREATE TABLE IF NOT EXISTS rejected_events (
    rejection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at  TEXT NOT NULL,
    source       TEXT NOT NULL,
    device_id    TEXT,
    reason       TEXT NOT NULL,
    payload      TEXT NOT NULL
);

-- Append-only: observations can never be changed or removed.
CREATE TRIGGER IF NOT EXISTS observations_no_update BEFORE UPDATE ON observations
BEGIN SELECT RAISE(ABORT, 'observations are append-only'); END;
CREATE TRIGGER IF NOT EXISTS observations_no_delete BEFORE DELETE ON observations
BEGIN SELECT RAISE(ABORT, 'observations are append-only'); END;

-- Measurement schedules (M2). Additive: older gateway files gain this table on next open.
CREATE TABLE IF NOT EXISTS measurement_schedules (
    schedule_seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id           TEXT NOT NULL UNIQUE,
    fingerprint  TEXT NOT NULL,
    subject_id   TEXT NOT NULL,
    metric       TEXT NOT NULL,
    supersedes   TEXT,
    received_at  TEXT NOT NULL,
    payload      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sched_subject_metric ON measurement_schedules (subject_id, metric);
CREATE TRIGGER IF NOT EXISTS schedules_no_update BEFORE UPDATE ON measurement_schedules
BEGIN SELECT RAISE(ABORT, 'schedules are append-only'); END;
CREATE TRIGGER IF NOT EXISTS schedules_no_delete BEFORE DELETE ON measurement_schedules
BEGIN SELECT RAISE(ABORT, 'schedules are append-only'); END;

-- Upstream delivery (M3). Cursors are operational metadata (monotonic, enforced in code);
-- failures are an append-only audit log.
CREATE TABLE IF NOT EXISTS upstream_cursors (
    destination TEXT PRIMARY KEY,
    acked_seq   INTEGER NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS upstream_failures (
    failure_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    destination    TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    server_seq     INTEGER NOT NULL,
    error          TEXT NOT NULL,
    recorded_at    TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS upstream_failures_no_update BEFORE UPDATE ON upstream_failures
BEGIN SELECT RAISE(ABORT, 'upstream failures are append-only'); END;
CREATE TRIGGER IF NOT EXISTS upstream_failures_no_delete BEFORE DELETE ON upstream_failures
BEGIN SELECT RAISE(ABORT, 'upstream failures are append-only'); END;

-- Immutable documents (M3): published references, environmental events. Append-only.
CREATE TABLE IF NOT EXISTS documents (
    doc_seq     INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    doc_key     TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    tag         TEXT,
    sort_time   TEXT,
    received_at TEXT NOT NULL,
    payload     TEXT NOT NULL,
    UNIQUE (kind, doc_key)
);
CREATE INDEX IF NOT EXISTS documents_kind_tag_time ON documents (kind, tag, sort_time);
CREATE TRIGGER IF NOT EXISTS documents_no_update BEFORE UPDATE ON documents
BEGIN SELECT RAISE(ABORT, 'documents are append-only'); END;
CREATE TRIGGER IF NOT EXISTS documents_no_delete BEFORE DELETE ON documents
BEGIN SELECT RAISE(ABORT, 'documents are append-only'); END;

-- Accepted-write audit (M3): which channel/client/device wrote each accepted observation.
CREATE TABLE IF NOT EXISTS write_audit (
    audit_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    server_seq     INTEGER NOT NULL,
    observation_id TEXT NOT NULL,
    channel        TEXT NOT NULL,
    client_id      TEXT,
    device_id      TEXT,
    recorded_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS write_audit_observation ON write_audit (observation_id);
CREATE TRIGGER IF NOT EXISTS write_audit_no_update BEFORE UPDATE ON write_audit
BEGIN SELECT RAISE(ABORT, 'write audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS write_audit_no_delete BEFORE DELETE ON write_audit
BEGIN SELECT RAISE(ABORT, 'write audit is append-only'); END;
"""

_TS = "%Y-%m-%dT%H:%M:%S.%fZ"  # fixed width, so lexicographic order == chronological order


def _ts(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime(_TS)


def _parse_ts(text: str) -> datetime:
    return datetime.strptime(text, _TS).replace(tzinfo=UTC)


class SqliteObservationRepository:
    def __init__(self, path: str | Path) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def add(self, observation: HealthObservation) -> AddOutcome:
        fingerprint = observation_fingerprint(observation)
        with self._lock:
            existing = self._conn.execute(
                "SELECT server_seq, payload FROM observations WHERE id = ?", (str(observation.id),)
            ).fetchone()
            if existing is not None:
                seq, stored_payload = existing
                # Re-fingerprint the stored row with the current model so additive schema fields
                # (with defaults) never turn a legitimate retry into a false conflict.
                stored_fp = observation_fingerprint(HealthObservation.model_validate_json(stored_payload))
                status = AddStatus.DUPLICATE if stored_fp == fingerprint else AddStatus.CONFLICT
                return AddOutcome(status, seq)
            cur = self._conn.execute(
                "INSERT INTO observations (id, fingerprint, subject_id, module, metric, device_id, "
                "data_origin, observed_at, received_at, payload) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    str(observation.id),
                    fingerprint,
                    observation.subject_id,
                    observation.module.value,
                    observation.metric,
                    observation.device_id,
                    observation.provenance.data_origin.value,
                    _ts(observation.observed_at),
                    _ts(datetime.now(UTC)),
                    observation.model_dump_json(),
                ),
            )
            return AddOutcome(AddStatus.INSERTED, int(cur.lastrowid))

    def get(self, observation_id: UUID) -> StoredObservation | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT server_seq, received_at, payload FROM observations WHERE id = ?",
                (str(observation_id),),
            ).fetchone()
        return self._stored(row) if row else None

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
        clauses: list[str] = []
        params: list[Any] = []
        if subject_id is not None:
            clauses.append("subject_id = ?")
            params.append(subject_id)
        if module is not None:
            clauses.append("module = ?")
            params.append(module.value)
        if data_origin is not None:
            clauses.append("data_origin = ?")
            params.append(data_origin.value)
        if since is not None:
            clauses.append("observed_at >= ?")
            params.append(_ts(since))
        if until is not None:
            clauses.append("observed_at < ?")
            params.append(_ts(until))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT payload FROM observations {where} ORDER BY observed_at, id LIMIT ?"  # noqa: S608
        with self._lock:
            rows = self._conn.execute(sql, [*params, limit]).fetchall()
        return [HealthObservation.model_validate_json(r[0]) for r in rows]

    def changes_since(
        self, cursor: int, *, limit: int = 500, subject_id: str | None = None
    ) -> list[StoredObservation]:
        sql = "SELECT server_seq, received_at, payload FROM observations WHERE server_seq > ?"
        params: list[Any] = [max(cursor, 0)]
        if subject_id is not None:
            sql += " AND subject_id = ?"
            params.append(subject_id)
        sql += " ORDER BY server_seq LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._stored(r) for r in rows]

    def head_seq(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COALESCE(MAX(server_seq), 0) FROM observations").fetchone()
        return int(row[0])

    def latest_by_device_metric(self) -> list[HealthObservation]:
        sql = (
            "SELECT payload FROM (SELECT payload, ROW_NUMBER() OVER ("
            "PARTITION BY COALESCE(device_id, ''), subject_id, metric "
            "ORDER BY observed_at DESC, server_seq DESC) AS rn FROM observations) WHERE rn = 1"
        )
        with self._lock:
            rows = self._conn.execute(sql).fetchall()
        out = [HealthObservation.model_validate_json(r[0]) for r in rows]
        return sorted(out, key=lambda o: (o.device_id or "", o.subject_id, o.metric))

    def record_rejection(
        self, *, source: str, device_id: str | None, reason: str, payload: dict[str, Any]
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO rejected_events (received_at, source, device_id, reason, payload) "
                "VALUES (?,?,?,?,?)",
                (_ts(datetime.now(UTC)), source, device_id, reason, json.dumps(payload, default=str)),
            )

    def rejection_count(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM rejected_events").fetchone()[0])

    def list_rejections(self, limit: int = 100) -> list[RejectedRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT rejection_id, received_at, source, device_id, reason, payload "
                "FROM rejected_events ORDER BY rejection_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            RejectedRecord(
                rejection_id=r[0],
                received_at=_parse_ts(r[1]),
                source=r[2],
                device_id=r[3],
                reason=r[4],
                payload=json.loads(r[5]),
            )
            for r in rows
        ]

    def add_schedule(self, schedule: MeasurementSchedule) -> AddOutcome:
        fingerprint = schedule_fingerprint(schedule)
        with self._lock:
            existing = self._conn.execute(
                "SELECT schedule_seq, payload FROM measurement_schedules WHERE id = ?",
                (str(schedule.id),),
            ).fetchone()
            if existing is not None:
                seq, stored_payload = existing
                stored_fp = schedule_fingerprint(MeasurementSchedule.model_validate_json(stored_payload))
                status = AddStatus.DUPLICATE if stored_fp == fingerprint else AddStatus.CONFLICT
                return AddOutcome(status, seq)
            cur = self._conn.execute(
                "INSERT INTO measurement_schedules (id, fingerprint, subject_id, metric, supersedes, "
                "received_at, payload) VALUES (?,?,?,?,?,?,?)",
                (
                    str(schedule.id),
                    fingerprint,
                    schedule.subject_id,
                    schedule.metric,
                    str(schedule.supersedes) if schedule.supersedes else None,
                    _ts(datetime.now(UTC)),
                    schedule.model_dump_json(),
                ),
            )
            return AddOutcome(AddStatus.INSERTED, int(cur.lastrowid))

    def get_schedule(self, schedule_id: UUID) -> MeasurementSchedule | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM measurement_schedules WHERE id = ?", (str(schedule_id),)
            ).fetchone()
        return MeasurementSchedule.model_validate_json(row[0]) if row else None

    def list_schedules(
        self, *, subject_id: str | None = None, metric: str | None = None, current_only: bool = False
    ) -> list[MeasurementSchedule]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload FROM measurement_schedules ORDER BY schedule_seq"
            ).fetchall()
        return filter_schedules(
            [MeasurementSchedule.model_validate_json(r[0]) for r in rows], subject_id, metric, current_only
        )

    def upstream_cursor(self, destination: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT acked_seq FROM upstream_cursors WHERE destination = ?", (destination,)
            ).fetchone()
        return int(row[0]) if row else 0

    def set_upstream_cursor(self, destination: str, server_seq: int) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT acked_seq FROM upstream_cursors WHERE destination = ?", (destination,)
            ).fetchone()
            if row and server_seq < int(row[0]):
                raise ValueError("upstream cursor cannot move backwards")
            self._conn.execute(
                "INSERT INTO upstream_cursors (destination, acked_seq, updated_at) VALUES (?,?,?) "
                "ON CONFLICT(destination) DO UPDATE SET acked_seq = excluded.acked_seq, "
                "updated_at = excluded.updated_at",
                (destination, server_seq, _ts(datetime.now(UTC))),
            )

    def record_upstream_failure(
        self, destination: str, observation_id: UUID, server_seq: int, error: str
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO upstream_failures (destination, observation_id, server_seq, error, recorded_at) "
                "VALUES (?,?,?,?,?)",
                (destination, str(observation_id), server_seq, error, _ts(datetime.now(UTC))),
            )

    def list_upstream_failures(
        self, destination: str | None = None, limit: int = 100
    ) -> list[UpstreamFailure]:
        sql = (
            "SELECT failure_id, destination, observation_id, server_seq, error, recorded_at "
            "FROM upstream_failures"
        )
        params: list[Any] = []
        if destination is not None:
            sql += " WHERE destination = ?"
            params.append(destination)
        sql += " ORDER BY failure_id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [
            UpstreamFailure(
                failure_id=r[0],
                destination=r[1],
                observation_id=UUID(r[2]),
                server_seq=r[3],
                error=r[4],
                recorded_at=_parse_ts(r[5]),
            )
            for r in rows
        ]

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
            existing = self._conn.execute(
                "SELECT doc_seq, payload FROM documents WHERE kind = ? AND doc_key = ?", (kind, key)
            ).fetchone()
            if existing is not None:
                seq, stored_payload = existing
                # Re-fingerprint with the current model (D-025): additive fields never cause false conflicts.
                stored_fp = document_fingerprint(type(doc).model_validate_json(stored_payload))
                status = AddStatus.DUPLICATE if stored_fp == fingerprint else AddStatus.CONFLICT
                return AddOutcome(status, seq)
            cur = self._conn.execute(
                "INSERT INTO documents (kind, doc_key, fingerprint, tag, sort_time, received_at, payload) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    kind,
                    key,
                    fingerprint,
                    tag,
                    _ts(sort_time) if sort_time else None,
                    _ts(datetime.now(UTC)),
                    doc.model_dump_json(),
                ),
            )
            return AddOutcome(AddStatus.INSERTED, int(cur.lastrowid))

    def get_document(self, kind: str, key: str, model: type[M]) -> M | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM documents WHERE kind = ? AND doc_key = ?", (kind, key)
            ).fetchone()
        return model.model_validate_json(row[0]) if row else None

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
        sql = "SELECT payload FROM documents WHERE kind = ?"
        params: list[Any] = [kind]
        if tag is not None:
            sql += " AND tag = ?"
            params.append(tag)
        if since is not None:
            sql += " AND sort_time >= ?"
            params.append(_ts(since))
        if until is not None:
            sql += " AND sort_time < ?"
            params.append(_ts(until))
        sql += " ORDER BY sort_time IS NULL, sort_time, doc_seq" if order_by_time else " ORDER BY doc_seq"
        sql += " LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [model.model_validate_json(r[0]) for r in rows]

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
            rows = self._conn.execute(
                "SELECT doc_seq, kind, doc_key, payload FROM documents "
                "WHERE doc_seq > ? ORDER BY doc_seq LIMIT ?",
                (max(cursor, 0), limit),
            ).fetchall()
        return [DocumentChange(seq=r[0], kind=r[1], key=r[2], payload=json.loads(r[3])) for r in rows]

    def document_head_seq(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COALESCE(MAX(doc_seq), 0) FROM documents").fetchone()[0])

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
            self._conn.execute(
                "INSERT INTO write_audit (server_seq, observation_id, channel, client_id, device_id, "
                "recorded_at) VALUES (?,?,?,?,?,?)",
                (server_seq, str(observation_id), channel, client_id, device_id, _ts(datetime.now(UTC))),
            )

    def list_writes(self, limit: int = 100) -> list[WriteAuditRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT audit_id, server_seq, observation_id, channel, client_id, device_id, recorded_at "
                "FROM write_audit ORDER BY audit_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            WriteAuditRecord(
                audit_id=r[0],
                server_seq=r[1],
                observation_id=UUID(r[2]),
                channel=r[3],
                client_id=r[4],
                device_id=r[5],
                recorded_at=_parse_ts(r[6]),
            )
            for r in rows
        ]

    @staticmethod
    def _stored(row: tuple[int, str, str]) -> StoredObservation:
        return StoredObservation(
            server_seq=row[0],
            received_at=_parse_ts(row[1]),
            observation=HealthObservation.model_validate_json(row[2]),
        )
