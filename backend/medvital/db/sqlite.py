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

from medvital.core.schema import DataOrigin, HealthObservation, ModuleId, observation_fingerprint
from medvital.db.repository import AddOutcome, AddStatus, RejectedRecord, StoredObservation

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
                "SELECT server_seq, fingerprint FROM observations WHERE id = ?", (str(observation.id),)
            ).fetchone()
            if existing is not None:
                seq, stored_fp = existing
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

    @staticmethod
    def _stored(row: tuple[int, str, str]) -> StoredObservation:
        return StoredObservation(
            server_seq=row[0],
            received_at=_parse_ts(row[1]),
            observation=HealthObservation.model_validate_json(row[2]),
        )
