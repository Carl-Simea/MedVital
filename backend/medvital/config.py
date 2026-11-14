"""Runtime configuration from environment variables (no extra dependency)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # When unset, the in-memory repository is used. Example:
    # postgresql://medvital:medvital@localhost:5432/medvital
    database_url: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        return cls(database_url=os.environ.get("MEDVITAL_DATABASE_URL") or None)
