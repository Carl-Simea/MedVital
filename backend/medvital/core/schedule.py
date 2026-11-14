"""Measurement schedules and the mission-relative time model (milestone M2).

A schedule says *when a measurement is planned*, never what its value is. Planned times are
expressed relative to mission anchors, as NASA protocols are (``L-13`` = 13 days before launch,
``R+1`` = 1 day after return), and are resolved to absolute UTC times only when a launch and a
return time are supplied. Resolved planned times are therefore *modeled* timestamps.

Schedules are immutable and append-only, like observations: a revision is a new schedule whose
``supersedes`` points at the old id. A schedule never creates, imputes or interpolates an
observation; coverage only reports which planned windows contain observations.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from medvital.core.schema import (
    DataOrigin,
    HealthObservation,
    LongText,
    MetricId,
    ModuleId,
    ShortText,
    SubjectId,
)

SCHEDULE_SCHEMA_VERSION = 1
MAX_EVENTS_PER_SCHEDULE = 200
MAX_RESOLVED_EVENTS = 2000


class Anchor(StrEnum):
    LAUNCH = "launch"  # "L" in NASA L-n notation
    RETURN = "return"  # "R" in NASA R+n notation


class MissionPhase(StrEnum):
    PREFLIGHT = "preflight"  # before launch
    INFLIGHT = "inflight"  # launch <= t < return
    POSTFLIGHT = "postflight"  # t >= return


class ScheduleBasis(StrEnum):
    PROTOCOL = "protocol"  # transcribed from a documented protocol; source_ref required
    SIMULATED = "simulated"  # a MEDVITAL test plan; timing is arbitrary, like simulated values


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _label(anchor: Anchor, offset_days: int) -> str:
    return f"{'L' if anchor is Anchor.LAUNCH else 'R'}{offset_days:+d}"


class SingleTimepoint(_Frozen):
    kind: Literal["single"] = "single"
    anchor: Anchor
    offset_days: int = Field(ge=-3650, le=3650)
    window_days: int = Field(default=0, ge=0, le=365, description="Tolerance either side of the planned day.")
    label: ShortText | None = Field(default=None, description="Defaults to L±n / R±n.")


class RecurringTimepoints(_Frozen):
    """Every ``every_days`` from (start_anchor + start_offset) to (end_anchor + end_offset), inclusive."""

    kind: Literal["recurring"] = "recurring"
    start_anchor: Anchor
    start_offset_days: int = Field(ge=-3650, le=3650)
    end_anchor: Anchor
    end_offset_days: int = Field(ge=-3650, le=3650)
    every_days: int = Field(ge=1, le=365)
    window_days: int = Field(default=0, ge=0, le=365)
    label: ShortText | None = None


ScheduleEvent = Annotated[SingleTimepoint | RecurringTimepoints, Field(discriminator="kind")]


class MeasurementSchedule(_Frozen):
    schema_version: int = SCHEDULE_SCHEMA_VERSION
    id: UUID
    subject_id: SubjectId
    metric: MetricId
    method: ShortText = Field(description="Measurement method, e.g. 'DXA', 'actigraphy', 'questionnaire'.")
    context: dict[str, str] = Field(default_factory=dict, description="Same keys as the metric's context.")
    events: list[ScheduleEvent] = Field(min_length=1, max_length=MAX_EVENTS_PER_SCHEDULE)
    basis: ScheduleBasis
    source: ShortText = Field(description="Who/what defined this plan.")
    source_ref: ShortText | None = Field(default=None, description="Protocol document, DOI or URL.")
    notes: LongText | None = None
    created_at: AwareDatetime
    supersedes: UUID | None = None

    @property
    def module(self) -> ModuleId:
        return ModuleId(self.metric.split(".", 1)[0])

    @field_validator("schema_version")
    @classmethod
    def _check_version(cls, v: int) -> int:
        if v != SCHEDULE_SCHEMA_VERSION:
            raise ValueError(f"unsupported schedule schema_version {v}")
        return v

    @model_validator(mode="after")
    def _check(self) -> Self:
        prefix = self.metric.split(".", 1)[0]
        if prefix not in {m.value for m in ModuleId}:
            raise ValueError(f"metric {self.metric!r} is not in a known module")
        if self.basis is ScheduleBasis.PROTOCOL and self.source_ref is None:
            raise ValueError("protocol-based schedules require source_ref")
        if self.supersedes == self.id:
            raise ValueError("a schedule cannot supersede itself")
        return self


def schedule_fingerprint(schedule: MeasurementSchedule) -> str:
    canonical = json.dumps(schedule.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- resolution


class MissionWindow(_Frozen):
    launch_at: AwareDatetime
    return_at: AwareDatetime

    @model_validator(mode="after")
    def _order(self) -> Self:
        if not self.return_at > self.launch_at:
            raise ValueError("return_at must be after launch_at")
        return self

    def anchor_time(self, anchor: Anchor) -> datetime:
        return self.launch_at if anchor is Anchor.LAUNCH else self.return_at

    def phase(self, t: datetime) -> MissionPhase:
        if t < self.launch_at:
            return MissionPhase.PREFLIGHT
        if t < self.return_at:
            return MissionPhase.INFLIGHT
        return MissionPhase.POSTFLIGHT


class ResolvedEvent(_Frozen):
    """A planned measurement time. ``planned_at`` is modeled (derived from mission anchors)."""

    schedule_id: UUID
    label: str
    planned_at: datetime
    window_start: datetime  # inclusive: planned_at - window_days
    window_end: datetime  # exclusive: planned_at + (window_days + 1) days, i.e. the planned day is 24 h long
    phase: MissionPhase
    time_origin: Literal[DataOrigin.MODELED] = DataOrigin.MODELED
    time_method: str = "mission anchor + whole-day offset (core.schedule v1)"


def resolve_schedule(schedule: MeasurementSchedule, mission: MissionWindow) -> list[ResolvedEvent]:
    out: list[ResolvedEvent] = []

    def emit(anchor: Anchor, offset: int, window: int, label: str | None) -> None:
        t = mission.anchor_time(anchor) + timedelta(days=offset)
        out.append(
            ResolvedEvent(
                schedule_id=schedule.id,
                label=label or _label(anchor, offset),
                planned_at=t,
                window_start=t - timedelta(days=window),
                window_end=t + timedelta(days=window + 1),
                phase=mission.phase(t),
            )
        )
        if len(out) > MAX_RESOLVED_EVENTS:
            raise ValueError(f"schedule resolves to more than {MAX_RESOLVED_EVENTS} events")

    for ev in schedule.events:
        if isinstance(ev, SingleTimepoint):
            emit(ev.anchor, ev.offset_days, ev.window_days, ev.label)
            continue
        start = mission.anchor_time(ev.start_anchor) + timedelta(days=ev.start_offset_days)
        end = mission.anchor_time(ev.end_anchor) + timedelta(days=ev.end_offset_days)
        if end < start:
            raise ValueError("recurring event ends before it starts for this mission")
        offset = ev.start_offset_days
        while mission.anchor_time(ev.start_anchor) + timedelta(days=offset) <= end:
            emit(ev.start_anchor, offset, ev.window_days, ev.label)
            offset += ev.every_days
    out.sort(key=lambda e: (e.planned_at, e.label))
    return out


# --------------------------------------------------------------------------- coverage


class EventCoverage(_Frozen):
    event: ResolvedEvent
    observed_counts: dict[str, int] = Field(description="Observations inside the window, per data origin.")


class ScheduleCoverage(_Frozen):
    schedule_id: UUID
    metric: str
    planned_events: int
    events_with_observations: dict[str, int] = Field(description="Per data origin; origins are never pooled.")
    events: list[EventCoverage]
    unscheduled_observations: dict[str, int] = Field(
        description="Matching observations outside every planned window, per data origin."
    )
    note: str = (
        "Coverage compares planned windows with recorded observations. Missing measurements stay "
        "missing: nothing is imputed or interpolated."
    )


def _matches(o: HealthObservation, schedule: MeasurementSchedule) -> bool:
    return (
        o.subject_id == schedule.subject_id
        and o.metric == schedule.metric
        and all(o.context.get(k) == v for k, v in schedule.context.items())
    )


def schedule_coverage(
    schedule: MeasurementSchedule,
    resolved: Sequence[ResolvedEvent],
    observations: Iterable[HealthObservation],
) -> ScheduleCoverage:
    relevant = [o for o in observations if _matches(o, schedule)]
    per_event: list[EventCoverage] = []
    in_any: set[UUID] = set()
    for ev in resolved:
        counts: dict[str, int] = {}
        for o in relevant:
            if ev.window_start <= o.observed_at < ev.window_end:
                counts[o.provenance.data_origin.value] = counts.get(o.provenance.data_origin.value, 0) + 1
                in_any.add(o.id)
        per_event.append(EventCoverage(event=ev, observed_counts=dict(sorted(counts.items()))))
    covered: dict[str, int] = {}
    for ec in per_event:
        for origin in ec.observed_counts:
            covered[origin] = covered.get(origin, 0) + 1
    outside: dict[str, int] = {}
    for o in relevant:
        if o.id not in in_any:
            outside[o.provenance.data_origin.value] = outside.get(o.provenance.data_origin.value, 0) + 1
    return ScheduleCoverage(
        schedule_id=schedule.id,
        metric=schedule.metric,
        planned_events=len(resolved),
        events_with_observations=dict(sorted(covered.items())),
        events=per_event,
        unscheduled_observations=dict(sorted(outside.items())),
    )
