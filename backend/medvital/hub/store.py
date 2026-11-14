"""The spacecraft's database (the "D1" of the demo). Plain SQLite, one file, thread-safe.

Tables mirror the team plan: astronauts + baselines, every burst, alerts, daily summaries, lab
results, space weather, and the ``outbox`` for Earth. The outbox schema is exactly the one
``spacecraft-sync/sync.js`` reads on a real Cloudflare Worker: ``outbox(id, body, created_at)``.

``synced`` remembers every record id NASA confirmed, so the hub can prove nothing was lost.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from medvital.hub.settings import CREW

SCHEMA = """
CREATE TABLE IF NOT EXISTS astronauts (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL,
    device_key TEXT NOT NULL, profile TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bursts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    astronaut_id TEXT NOT NULL, seq INTEGER, time TEXT NOT NULL, received_at TEXT NOT NULL,
    heart_rate REAL, spo2 REAL, state TEXT, dose_rate REAL, total_dose REAL,
    scenario TEXT, quality TEXT NOT NULL, check_note TEXT, alert TEXT
);
CREATE INDEX IF NOT EXISTS bursts_by_astronaut ON bursts (astronaut_id, id);
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY, astronaut_id TEXT NOT NULL, code TEXT NOT NULL, reason TEXT NOT NULL,
    message TEXT NOT NULL, ai_message TEXT, ai_source TEXT, time TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS summaries (
    id TEXT PRIMARY KEY, astronaut_id TEXT NOT NULL, mission_day INTEGER NOT NULL, time TEXT NOT NULL,
    text TEXT NOT NULL, facts TEXT NOT NULL, ai_source TEXT NOT NULL, check_note TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS labs (
    id TEXT PRIMARY KEY, astronaut_id TEXT NOT NULL, time TEXT NOT NULL, ivalues TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS space_weather (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, event_time TEXT NOT NULL, received_at TEXT NOT NULL,
    active_until TEXT, summary TEXT NOT NULL, link TEXT, source TEXT NOT NULL, replay INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS rejected (
    id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL, astronaut_id TEXT,
    reason TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY, body TEXT NOT NULL, created_at TEXT NOT NULL);
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
    "alerts",
    "summaries",
    "labs",
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
            self._db.executescript(SCHEMA)
            for c in CREW:  # seed the crew once; keys are generated on first start ("pairing")
                self._db.execute(
                    "INSERT OR IGNORE INTO astronauts (id, name, role, device_key, profile)"
                    " VALUES (?,?,?,?,?)",
                    (c.astronaut_id, c.name, c.role, secrets.token_urlsafe(16), json.dumps(c.to_json())),
                )

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

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ------------------------------------------------------------------ crew
    def astronauts(self) -> list[dict[str, Any]]:
        rows = self.all("SELECT * FROM astronauts ORDER BY id")
        for r in rows:
            r["profile"] = json.loads(r["profile"])
        return rows

    def astronaut(self, astronaut_id: str) -> dict[str, Any] | None:
        r = self.one("SELECT * FROM astronauts WHERE id = ?", (astronaut_id,))
        if r:
            r["profile"] = json.loads(r["profile"])
        return r

    # ------------------------------------------------------------------ bursts
    def add_burst(self, b: dict[str, Any]) -> int:
        return self.run(
            "INSERT INTO bursts (astronaut_id, seq, time, received_at, heart_rate, spo2, state, dose_rate,"
            " total_dose, scenario, quality, check_note, alert) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                b["astronautId"],
                b.get("seq"),
                b["time"],
                now_iso(),
                b["heartRate"],
                b["spo2"],
                b["state"],
                b["doseRate"],
                b["totalDose"],
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

    def burst_count(self, astronaut_id: str) -> int:
        return self.scalar("SELECT COUNT(*) FROM bursts WHERE astronaut_id = ?", (astronaut_id,)) or 0

    # ------------------------------------------------------------------ outbox / records
    def to_outbox(self, record: dict[str, Any]) -> None:
        """Every record for Earth: remembered in ``records`` (forever) and queued in ``outbox``."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO records (id, type, astronaut_id, created_at) VALUES (?,?,?,?)",
                (record["id"], record["type"], record["astronautId"], now_iso()),
            )
            self._db.execute(
                "INSERT OR IGNORE INTO outbox (id, body, created_at) VALUES (?,?,?)",
                (record["id"], json.dumps(record), now_iso()),
            )

    def outbox_batch(self, limit: int) -> list[dict[str, Any]]:
        return self.all("SELECT id, body FROM outbox ORDER BY created_at ASC, id ASC LIMIT ?", (limit,))

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
