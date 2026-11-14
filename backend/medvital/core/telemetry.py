"""Wire contract between wearables and the spacecraft gateway (briefing §8).

The eleven contract fields are exactly: event_id, device_id, crew_id, timestamp, domain,
indicator, value, unit, source, quality, synthetic. Three optional extension fields
(``source_ref``, ``generator_version``, ``seed``) carry the provenance the storage schema
requires, so a gateway never has to invent a seed or a reference:

* ``synthetic: true``  -> ``generator_version`` and ``seed`` required (simulated data);
* ``synthetic: false`` -> ``source_ref`` required (measured data).

The gateway converts each event into a ``HealthObservation`` (see ``medvital.telemetry``).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from medvital.core.schema import DeviceId, ModuleId, Quality, ShortText, SubjectId

EventId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")]
Indicator = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: EventId = Field(description="Unique per device; e.g. 'EVT-000001'. Retries reuse the same id.")
    device_id: DeviceId
    crew_id: SubjectId
    timestamp: AwareDatetime = Field(description="When the device took the reading (timezone required).")
    domain: ModuleId
    indicator: Indicator = Field(description="Metric name inside the domain, e.g. 'heart_rate'.")
    value: float = Field(allow_inf_nan=False)
    unit: ShortText
    source: ShortText = Field(description="What produced it, e.g. 'simulated_sensor'.")
    quality: Quality
    synthetic: bool = Field(description="True for simulated data. Never true for measured data.")

    # Optional provenance extensions (see module docstring).
    source_ref: ShortText | None = None
    generator_version: ShortText | None = None
    seed: int | None = None
    uncertainty: float | None = Field(
        default=None, ge=0, allow_inf_nan=False, description="Standard uncertainty in `unit`; None = unknown."
    )

    @model_validator(mode="after")
    def _check_provenance_inputs(self) -> Self:
        if self.synthetic:
            if self.generator_version is None or self.seed is None:
                raise ValueError("synthetic events require generator_version and seed")
        elif self.source_ref is None:
            raise ValueError("non-synthetic (measured) events require source_ref")
        return self


class TelemetryStatus(StrEnum):
    ACCEPTED = "accepted"  # newly stored
    DUPLICATE = "duplicate"  # identical event already stored (safe retry)
    REJECTED = "rejected"  # invalid; recorded in the rejection audit log, never silently dropped


class TelemetryResult(BaseModel):
    event_id: str | None = None
    status: TelemetryStatus
    server_seq: int | None = None
    error: str | None = None


class TelemetryResponse(BaseModel):
    results: list[TelemetryResult]
    accepted: int
    duplicate: int
    rejected: int
