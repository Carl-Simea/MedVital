"""The spacecraft's database (the "D1" of the demo). Plain SQLite, one file, thread-safe.

Tables: astronauts (+ pre-flight baseline and report), bursts, tests (onboard measurements and
lab results), alerts, summaries, events (mission schedule and real space weather), space_weather
(demo replays), rejected, outbox (+ urgent flag), records, synced, agent_log, meta.

The outbox (``id, body, created_at, urgent``) is drained to Earth: the Cloudflare Worker (``cloudflare/``) or
the NASA receiver directly.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS astronauts (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, device_key TEXT NOT NULL,
    profile TEXT NOT NULL, report TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bursts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    astronaut_id TEXT NOT NULL, seq INTEGER, time TEXT NOT NULL, received_at TEXT NOT NULL, mission_minute REAL,
    heart_rate REAL, spo2 REAL, state TEXT, dose_rate REAL, total_dose REAL, resp_rate REAL, skin_temp REAL,
    rad_ref TEXT, scenario TEXT, quality TEXT NOT NULL, check_note TEXT, alert TEXT
);
CREATE INDEX IF NOT EXISTS bursts_by_astronaut ON bursts (astronaut_id, id);
CREATE TABLE IF NOT EXISTS tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT, astronaut_id TEXT NOT NULL, mission_minute REAL NOT NULL,
    key TEXT NOT NULL, value REAL NOT NULL, origin TEXT NOT NULL, source TEXT NOT NULL, time TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tests_by_key ON tests (astronaut_id, key, id);
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY, astronaut_id TEXT NOT NULL, code TEXT NOT NULL, reason TEXT NOT NULL,
    message TEXT NOT NULL, ai_message TEXT, ai_source TEXT, time TEXT NOT NULL, mission_minute REAL,
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS summaries (
    id TEXT PRIMARY KEY, astronaut_id TEXT NOT NULL, mission_day INTEGER NOT NULL, time TEXT NOT NULL,
    text TEXT NOT NULL, facts TEXT NOT NULL, ai_source TEXT NOT NULL, check_note TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, m_start REAL NOT NULL, m_end REAL NOT NULL, kind TEXT NOT NULL,
    astronaut_id TEXT, title TEXT NOT NULL, detail TEXT, source TEXT NOT NULL, link TEXT, sw_type TEXT,
    status TEXT NOT NULL DEFAULT 'planned'
);
CREATE INDEX IF NOT EXISTS events_by_time ON events (m_start);
CREATE TABLE IF NOT EXISTS space_weather (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, event_time TEXT NOT NULL, received_at TEXT NOT NULL,
    active_until TEXT, summary TEXT NOT NULL, link TEXT, source TEXT NOT NULL, replay INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS rejected (
    id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL, astronaut_id TEXT,
    reason TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    id TEXT PRIMARY KEY, body TEXT NOT NULL, created_at TEXT NOT NULL, urgent INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY, type TEXT NOT NULL, astronaut_id TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS synced (id TEXT PRIMARY KEY, synced_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL, astronaut_id TEXT NOT NULL,
    question TEXT NOT NULL, answer TEXT NOT NULL, source TEXT NOT NULL
);
"""

TABLES = (
    "astronauts",
    "bursts",
    "tests",
    "alerts",
    "summaries",
    "events",
    "space_weather",
    "rejected",
    "outbox",
    "records",
    "synced",
    "agent_log",
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class HubStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock, self._db:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(SCHEMA)

    # ------------------------------------------------------------------ generic helpers
    def all(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    def one(self, sql: str, args: tuple = ()) -> dict[str, Any] | None:
        rows = self.all(sql, args)
        return rows[0] if rows else None

    def scalar(self, sql: str, args: tuple = ()) -> Any:
        with self._lock:
            row = self._db.execute(sql, args).fetchone()
        return row[0] if row else None

    def run(self, sql: str, args: tuple = ()) -> int:
        with self._lock, self._db:
            return self._db.execute(sql, args).lastrowid or 0

    def many(self, sql: str, rows: list[tuple]) -> None:
        with self._lock, self._db:
            self._db.executemany(sql, rows)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def meta(self, key: str, value: str | None = None) -> str | None:
        if value is not None:
            self.run("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", (key, value))
            return value
        return self.scalar("SELECT value FROM meta WHERE key=?", (key,))

    # ------------------------------------------------------------------ crew
    def add_astronaut(self, profile: dict[str, Any], report: str | None = None) -> bool:
        """Insert once; returns True when the astronaut is new. The device key is the wearable's secret."""
        with self._lock, self._db:
            cur = self._db.execute(
                "INSERT OR IGNORE INTO astronauts (id, name, role, device_key, profile, report, created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    profile["astronaut_id"],
                    profile["name"],
                    profile["role"],
                    secrets.token_urlsafe(16),
                    json.dumps(profile),
                    report,
                    now_iso(),
                ),
            )
            return cur.rowcount == 1

    def astronauts(self) -> list[dict[str, Any]]:
        rows = self.all("SELECT * FROM astronauts ORDER BY created_at, id")
        for r in rows:
            r["profile"] = json.loads(r["profile"])
        return rows

    def astronaut(self, astronaut_id: str) -> dict[str, Any] | None:
        r = self.one("SELECT * FROM astronauts WHERE id = ?", (astronaut_id,))
        if r:
            r["profile"] = json.loads(r["profile"])
        return r

    # ------------------------------------------------------------------ bursts and tests
    def add_burst(self, b: dict[str, Any]) -> int:
        return self.run(
            "INSERT INTO bursts (astronaut_id, seq, time, received_at, mission_minute, heart_rate, spo2, state,"
            " dose_rate, total_dose, resp_rate, skin_temp, rad_ref, scenario, quality, check_note, alert)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                b["astronautId"],
                b.get("seq"),
                b["time"],
                now_iso(),
                b.get("missionMinute"),
                b["heartRate"],
                b["spo2"],
                b["state"],
                b["doseRate"],
                b["totalDose"],
                b.get("respRate"),
                b.get("skinTemp"),
                b.get("radRef"),
                b.get("scenario"),
                b["quality"],
                b.get("checkNote"),
                None,
            ),
        )

    def set_burst_alert(self, burst_id: int, code: str | None) -> None:
        self.run("UPDATE bursts SET alert = ? WHERE id = ?", (code, burst_id))

    def recent_bursts(self, astronaut_id: str, limit: int = 120) -> list[dict[str, Any]]:
        rows = self.all(
            "SELECT * FROM bursts WHERE astronaut_id = ? ORDER BY id DESC LIMIT ?", (astronaut_id, limit)
        )
        return rows[::-1]

    def bursts_between(self, astronaut_id: str, m0: float, m1: float) -> list[dict[str, Any]]:
        return self.all(
            "SELECT * FROM bursts WHERE astronaut_id=? AND mission_minute>=? AND mission_minute<? "
            "ORDER BY id",
            (astronaut_id, m0, m1),
        )

    def burst_count(self, astronaut_id: str) -> int:
        return self.scalar("SELECT COUNT(*) FROM bursts WHERE astronaut_id = ?", (astronaut_id,)) or 0

    def add_tests(
        self, astronaut_id: str, m: float, values: dict[str, float], origin: str, source: str
    ) -> None:
        t = now_iso()
        self.many(
            "INSERT INTO tests (astronaut_id, mission_minute, key, value, origin, source, time)"
            " VALUES (?,?,?,?,?,?,?)",
            [(astronaut_id, m, k, float(v), origin, source, t) for k, v in values.items()],
        )

    def latest_tests(self, astronaut_id: str) -> dict[str, dict[str, Any]]:
        rows = self.all(
            "SELECT t.* FROM tests t JOIN (SELECT key, MAX(id) mid FROM tests WHERE astronaut_id=? "
            "GROUP BY key) x ON t.id = x.mid",
            (astronaut_id,),
        )
        return {r["key"]: r for r in rows}

    def test_history(self, astronaut_id: str, key: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.all(
            "SELECT mission_minute, value, origin FROM tests WHERE astronaut_id=? AND key=? "
            "ORDER BY id DESC LIMIT ?",
            (astronaut_id, key, limit),
        )
        return rows[::-1]

    # ------------------------------------------------------------------ outbox / records
    def to_outbox(self, record: dict[str, Any], urgent: bool = False) -> None:
        """Every record for Earth: remembered in ``records`` (forever) and queued in ``outbox``."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO records (id, type, astronaut_id, created_at) VALUES (?,?,?,?)",
                (record["id"], record["type"], record.get("astronautId") or "crew", now_iso()),
            )
            self._db.execute(
                "INSERT OR IGNORE INTO outbox (id, body, created_at, urgent) VALUES (?,?,?,?)",
                (record["id"], json.dumps(record), now_iso(), int(urgent)),
            )

    def outbox_batch(self, limit: int, urgent_only: bool = False) -> list[dict[str, Any]]:
        where = "WHERE urgent = 1 " if urgent_only else ""
        return self.all(
            f"SELECT id, body FROM outbox {where}ORDER BY created_at ASC, id ASC LIMIT ?", (limit,)
        )

    def confirm(self, ids: list[str]) -> int:
        if not ids:
            return 0
        t = now_iso()
        with self._lock, self._db:
            self._db.executemany(
                "INSERT OR IGNORE INTO synced (id, synced_at) VALUES (?,?)", [(i, t) for i in ids]
            )
            marks = ",".join("?" * len(ids))
            return self._db.execute(f"DELETE FROM outbox WHERE id IN ({marks})", tuple(ids)).rowcount

    def counts(self) -> dict[str, int]:
        return {t: self.scalar(f"SELECT COUNT(*) FROM {t}") or 0 for t in TABLES}
