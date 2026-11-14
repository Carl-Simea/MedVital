"""The shared health observation schema used by all four health modules.

An observation is one value of one metric for one astronaut at one instant. It is immutable
and identified by a client-generated UUID, which makes ingest idempotent and offline sync
conflict-free (see docs/ARCHITECTURE.md).
"""

from __future__ import annotations

from datetime import UTC
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from medvital.core.provenance import Provenance

SCHEMA_VERSION = 1

ASTRONAUT_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
METRIC_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"


class ModuleId(StrEnum):
    RADIATION = "radiation"
    BONE = "bone"
    CARDIOVASCULAR = "cardiovascular"
    BEHAVIORAL = "behavioral"


class HealthObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    id: UUID
    astronaut_id: str = Field(pattern=ASTRONAUT_ID_PATTERN)
    module: ModuleId
    metric: str = Field(pattern=METRIC_PATTERN)
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1, max_length=32)
    # Timezone-aware; normalised to UTC.
    observed_at: AwareDatetime
    provenance: Provenance
    # Small string tags such as {"site": "lumbar_spine"}. Never free-text clinical notes.
    context: dict[str, str] = Field(default_factory=dict)
    # Device that first recorded the observation (offline clients).
    device_id: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("observed_at")
    @classmethod
    def _to_utc(cls, value: AwareDatetime) -> AwareDatetime:
        return value.astimezone(UTC)

    @field_validator("context")
    @classmethod
    def _bounded_context(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 16:
            raise ValueError("context may have at most 16 entries")
        for key, item in value.items():
            if not key or len(key) > 64 or len(item) > 200:
                raise ValueError("context keys must be 1-64 chars and values at most 200 chars")
        return value
