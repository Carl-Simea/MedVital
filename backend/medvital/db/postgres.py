"""PostgreSQL implementation of the observation repository.

STATUS: architecture skeleton. It is written against psycopg 3 and schema.sql but has NOT been
run against a live database in this repository's test suite. Treat it as unverified until an
integration test with a real PostgreSQL instance exists (see docs/DECISIONS.md).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from medvital.core.observation import HealthObservation, ModuleId
from medvital.core.provenance import DataOrigin
from medvital.db.repository import AddResult, ChangePage

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

_INSERT = """
INSERT INTO health_observations
  (id, schema_version, astronaut_id, module, metric, value, unit, observed_at,
   origin, provenance, context, device_id, payload)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO NOTHING
RETURNING server_seq
"""


class PostgresObservationRepository:
    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
            from psycopg.types.json import Jsonb
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "PostgreSQL support requires the optional extra: pip install -e '.[postgres]'"
            ) from exc
        self._psycopg: Any = psycopg
        self._jsonb: Any = Jsonb
        self._dsn = dsn

    def _connect(self) -> Any:
        return self._psycopg.connect(self._dsn)

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))

    def add_many(self, observations: Sequence[HealthObservation]) -> AddResult:
        result = AddResult()
        with self._connect() as conn:
            for obs in observations:
                payload = obs.model_dump(mode="json")
                row = conn.execute(
                    _INSERT,
                    (
                        obs.id,
                        obs.schema_version,
                        obs.astronaut_id,
                        obs.module.value,
                        obs.metric,
                        obs.value,
                        obs.unit,
                        obs.observed_at,
                        obs.provenance.origin.value,
                        self._jsonb(payload["provenance"]),
                        self._jsonb(payload["context"]),
                        obs.device_id,
                        self._jsonb(payload),
                    ),
                ).fetchone()
                if row is not None:
                    result.accepted.append(obs.id)
                    continue
                existing = conn.execute(
                    "SELECT payload FROM health_observations WHERE id = %s", (obs.id,)
                ).fetchone()
                if existing is not None and existing[0] == payload:
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
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("astronaut_id", astronaut_id),
            ("module", module.value if module else None),
            ("metric", metric),
            ("origin", origin.value if origin else None),
        ):
            if value is not None:
                clauses.append(f"{column} = %s")
                params.append(value)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT payload FROM health_observations {where} ORDER BY observed_at, id LIMIT %s"
        with self._connect() as conn:
            rows = conn.execute(sql, (*params, limit)).fetchall()
        return [HealthObservation.model_validate(r[0]) for r in rows]

    def changes_since(self, cursor: int, limit: int) -> ChangePage:
        if cursor < 0 or limit < 1:
            raise ValueError("cursor must be >= 0 and limit >= 1")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT server_seq, payload FROM health_observations "
                "WHERE server_seq > %s ORDER BY server_seq LIMIT %s",
                (cursor, limit + 1),
            ).fetchall()
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = page[-1][0] if page else cursor
        return ChangePage(
            [HealthObservation.model_validate(r[1]) for r in page], next_cursor, has_more
        )
