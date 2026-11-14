"""Environment-driven configuration. No secrets are given defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    repository: str = "memory"  # "memory" | "sqlite" | "postgres"
    database_url: str | None = None
    sqlite_path: str = "medvital-gateway.db"
    # Gateway rejects telemetry stamped further in the future than this (clock-skew guard).
    # Engineering default, not a scientific value.
    max_future_skew_seconds: int = 300
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)

    @classmethod
    def from_env(cls) -> Settings:
        origins = os.environ.get("MEDVITAL_CORS_ORIGINS", "http://localhost:5173")
        return cls(
            repository=os.environ.get("MEDVITAL_REPOSITORY", "memory").strip().lower(),
            database_url=os.environ.get("MEDVITAL_DATABASE_URL") or None,
            sqlite_path=os.environ.get("MEDVITAL_SQLITE_PATH", "medvital-gateway.db"),
            max_future_skew_seconds=int(os.environ.get("MEDVITAL_MAX_FUTURE_SKEW_SECONDS", "300")),
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        )
