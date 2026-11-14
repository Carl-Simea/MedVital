"""Published research values as cited, read-only reference records (D-019, implemented in M3).

A ``PublishedReference`` is *never* a ``HealthObservation``: a cohort mean from a paper is not
any astronaut's reading. References may be displayed beside a series or named as a cited,
configured assumption in a modeled value's provenance; they are never pooled with observations
and never become clinical thresholds (rule 3).
"""

from __future__ import annotations

import hashlib
import json
import math
from enum import StrEnum
from typing import Annotated, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from medvital.core.schema import LongText, MetricId, ShortText

REFERENCE_SCHEMA_VERSION = 1

ReferenceId = Annotated[str, StringConstraints(pattern=r"^REF-[A-Z0-9][A-Z0-9-]{2,63}$")]
RequiredText = Annotated[str, StringConstraints(min_length=1, max_length=2000)]


class Verification(StrEnum):
    VERIFIED_AT_SOURCE = "verified_at_source"  # a person read the value in the primary source
    UNVERIFIED = "unverified"  # stored, but must render as unverified


class ReferencePopulation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    description: RequiredText
    species: ShortText
    n: int | None = Field(default=None, ge=1, description="Sample size as reported; None if not reported.")
    cohort: ShortText | None = None
    mission_type: ShortText | None = Field(default=None, description="e.g. 'ISS long-duration', 'bed rest'.")


class PublishedReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = REFERENCE_SCHEMA_VERSION
    reference_id: ReferenceId
    citation: RequiredText = Field(description="Authors, title, venue, year.")
    source_identifier: ShortText = Field(description="DOI, PMID, NTRS id or dataset accession.")
    verification: Verification
    verified_by: ShortText | None = None
    verified_at: AwareDatetime | None = None
    quantity: ShortText = Field(description="What the value describes, in the source's terms.")
    metric: MetricId | None = Field(default=None, description="Registered metric this relates to, if any.")
    unit: ShortText
    statistic: ShortText = Field(description="e.g. 'mean', 'median', 'SD', 'reported range'.")
    value: float | None = Field(default=None, allow_inf_nan=False)
    interval_lower: float | None = Field(default=None, allow_inf_nan=False)
    interval_upper: float | None = Field(default=None, allow_inf_nan=False)
    interval_kind: ShortText | None = Field(default=None, description="e.g. '95% CI', 'min-max'.")
    population: ReferencePopulation
    context: dict[str, str] = Field(default_factory=dict, description="Site, method, posture, timepoint...")
    limitations: RequiredText
    retrieved_at: AwareDatetime
    notes: LongText | None = None
    supersedes: ReferenceId | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.schema_version != REFERENCE_SCHEMA_VERSION:
            raise ValueError(f"unsupported reference schema_version {self.schema_version}")
        has_interval = self.interval_lower is not None or self.interval_upper is not None
        if self.value is None and not has_interval:
            raise ValueError("a reference needs a value or an interval")
        if has_interval:
            if self.interval_lower is None or self.interval_upper is None or self.interval_kind is None:
                raise ValueError("an interval needs interval_lower, interval_upper and interval_kind")
            if self.interval_lower > self.interval_upper:
                raise ValueError("interval_lower must be <= interval_upper")
        if self.verification is Verification.VERIFIED_AT_SOURCE and (
            self.verified_by is None or self.verified_at is None
        ):
            raise ValueError("verified_at_source requires verified_by and verified_at")
        if self.verification is Verification.UNVERIFIED and self.verified_at is not None:
            raise ValueError("an unverified reference cannot carry verified_at")
        if self.supersedes == self.reference_id:
            raise ValueError("a reference cannot supersede itself")
        for v in (self.value, self.interval_lower, self.interval_upper):
            if v is not None and not math.isfinite(v):
                raise ValueError("values must be finite")
        return self


def reference_fingerprint(reference: PublishedReference) -> str:
    canonical = json.dumps(reference.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
