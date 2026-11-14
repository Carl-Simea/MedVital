"""Choose a repository implementation from settings."""

from __future__ import annotations

from medvital.config import Settings
from medvital.db.repository import InMemoryObservationRepository, ObservationRepository


def make_repository(settings: Settings) -> ObservationRepository:
    if settings.database_url:
        from medvital.db.postgres import PostgresObservationRepository

        repo = PostgresObservationRepository(settings.database_url)
        repo.init_schema()
        return repo
    return InMemoryObservationRepository()
