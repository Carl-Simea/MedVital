"""Migration compatibility: a station database created by the previous release (commit 1bfb073)
opens under the current code with its data intact; new tables are added, nothing is altered."""

import sqlite3

from conftest import make_obs
from medvital.core.schema import HealthObservation, observation_fingerprint
from medvital.db.repository import AddStatus
from medvital.db.sqlite import SqliteObservationRepository
from medvital.records_service import list_missions

# Verbatim copy of the SQLite schema at commit 1bfb073 (do not edit: it is the migration baseline).
PREVIOUS_SCHEMA = """
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
"""


def _legacy_db(path):
    o = make_obs("behavioral.sleep_duration", 7.0)
    payload = o.model_dump(mode="json")
    del payload["uncertainty"]  # the field did not exist in that release
    conn = sqlite3.connect(path)
    conn.executescript(PREVIOUS_SCHEMA)
    conn.execute(
        "INSERT INTO observations (id, fingerprint, subject_id, module, metric, device_id, data_origin, "
        "observed_at, received_at, payload) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            str(o.id),
            "legacy",
            o.subject_id,
            o.module.value,
            o.metric,
            None,
            "simulated",
            "2030-01-01T00:00:00.000000Z",
            "2030-01-01T00:00:00.000000Z",
            HealthObservation.model_validate(payload).model_dump_json(exclude={"uncertainty"}),
        ),
    )
    conn.execute(
        "INSERT INTO upstream_cursors (destination, acked_seq, updated_at) VALUES ('spacecraft', 1, 'x')"
    )
    conn.commit()
    conn.close()
    return o


def test_previous_release_database_upgrades_in_place(tmp_path):
    path = tmp_path / "legacy.db"
    o = _legacy_db(path)
    repo = SqliteObservationRepository(path)  # applies the current schema (additive)
    tables = {r[0] for r in repo._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "observations",
        "rejected_events",
        "measurement_schedules",
        "upstream_cursors",
        "upstream_failures",
        "documents",
        "write_audit",
    } <= tables
    stored = repo.get(o.id).observation
    assert stored.value == 7.0 and stored.uncertainty is None  # unknown stays unknown
    assert repo.upstream_cursor("spacecraft") == 1  # cursor preserved
    assert repo.add(o).status is AddStatus.DUPLICATE  # legacy row: retry is a duplicate, not a conflict
    assert list_missions(repo) == []
    new = make_obs("behavioral.sleep_duration", 6.0)
    assert repo.add(new).status is AddStatus.INSERTED and repo.head_seq() == 2
    repo.close()
    reopened = SqliteObservationRepository(path)  # idempotent schema application
    assert reopened.head_seq() == 2 and observation_fingerprint(reopened.get(o.id).observation)
    reopened.close()


def test_upgrade_keeps_append_only_guarantees(tmp_path):
    path = tmp_path / "legacy.db"
    _legacy_db(path)
    SqliteObservationRepository(path).close()
    conn = sqlite3.connect(path)
    import pytest

    for sql in ("UPDATE observations SET subject_id = 'X'", "DELETE FROM observations"):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(sql)
    conn.close()
