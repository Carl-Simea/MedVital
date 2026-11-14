"""PostgreSQL repository — architecture skeleton only (docs/DECISIONS.md D-006).

The schema is in ``schema.sql`` and the contract is ``ObservationRepository``. This
class intentionally raises ``NotImplementedError`` rather than pretending to work: it
could not be exercised against a real server yet. Implementation checklist:

1. ``pip install -e "backend[postgres]"`` (psycopg 3).
2. ``add``: ``INSERT ... ON CONFLICT (id) DO NOTHING RETURNING server_seq``; when nothing is
   returned, ``SELECT fingerprint, server_seq`` and return DUPLICATE or CONFLICT.
3. ``changes_since``: ``WHERE server_seq > %s ORDER BY server_seq LIMIT %s``.
4. Run the shared repository contract tests against it (see tests/test_repository.py).
"""

from __future__ import annotations


class PostgresObservationRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        raise NotImplementedError(
            "PostgreSQL repository is not implemented yet; use MEDVITAL_REPOSITORY=memory. "
            "See backend/medvital/db/postgres.py for the implementation checklist."
        )
