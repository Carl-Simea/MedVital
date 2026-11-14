from __future__ import annotations

from medvital.config import Settings
from medvital.db.postgres import PostgresObservationRepository
from medvital.db.repository import InMemoryObservationRepository, ObservationRepository
from medvital.db.sqlite import SqliteObservationRepository


def build_repository(settings: Settings) -> ObservationRepository:
    if settings.repository == "memory":
        return InMemoryObservationRepository()
    if settings.repository == "sqlite":
        return SqliteObservationRepository(settings.sqlite_path)  # type: ignore[return-value]
    if settings.repository == "postgres":
        if not settings.database_url:
            raise RuntimeError("MEDVITAL_REPOSITORY=postgres requires MEDVITAL_DATABASE_URL")
        return PostgresObservationRepository(settings.database_url)  # type: ignore[return-value]
    raise RuntimeError(f"unknown MEDVITAL_REPOSITORY {settings.repository!r}")
