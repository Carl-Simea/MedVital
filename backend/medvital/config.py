"""Environment-driven configuration. No secrets are given defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    repository: str = "memory"  # "memory" | "postgres"
    database_url: str | None = None
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)

    @classmethod
    def from_env(cls) -> Settings:
        origins = os.environ.get("MEDVITAL_CORS_ORIGINS", "http://localhost:5173")
        return cls(
            repository=os.environ.get("MEDVITAL_REPOSITORY", "memory").strip().lower(),
            database_url=os.environ.get("MEDVITAL_DATABASE_URL") or None,
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        )
