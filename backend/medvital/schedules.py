"""Single write path for measurement schedules (mirrors ``ingest.py`` for observations)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from medvital.core.module_spec import ModuleRegistry
from medvital.core.schedule import MeasurementSchedule
from medvital.db.repository import AddStatus, ScheduleRepository


class ScheduleWriteResult(BaseModel):
    schedule_id: UUID
    status: Literal["accepted", "duplicate", "rejected"]
    schedule_seq: int | None = None
    error: str | None = None


def schedule_problem(
    schedule: MeasurementSchedule, registry: ModuleRegistry, repo: ScheduleRepository
) -> str | None:
    definition = registry.metric_definition(schedule.metric)
    if definition is None:
        return f"unknown metric {schedule.metric!r}"
    allowed = set(definition.required_context) | set(definition.optional_context)
    unknown = sorted(set(schedule.context) - allowed)
    if unknown:
        return f"{schedule.metric} does not accept context keys: {', '.join(unknown)}"
    if schedule.supersedes is not None:
        previous = repo.get_schedule(schedule.supersedes)
        if previous is None:
            return "supersedes refers to an unknown schedule"
        if (previous.subject_id, previous.metric) != (schedule.subject_id, schedule.metric):
            return "a revision must keep the subject and metric of the schedule it supersedes"
    return None


def store_schedule(
    repo: ScheduleRepository, registry: ModuleRegistry, schedule: MeasurementSchedule
) -> ScheduleWriteResult:
    problem = schedule_problem(schedule, registry, repo)
    if problem:
        return ScheduleWriteResult(schedule_id=schedule.id, status="rejected", error=problem)
    outcome = repo.add_schedule(schedule)
    if outcome.status is AddStatus.CONFLICT:
        return ScheduleWriteResult(
            schedule_id=schedule.id,
            status="rejected",
            schedule_seq=outcome.server_seq,
            error="a schedule with this id already exists with different content; schedules are immutable "
            "— submit a revision with `supersedes`",
        )
    status = "accepted" if outcome.status is AddStatus.INSERTED else "duplicate"
    return ScheduleWriteResult(schedule_id=schedule.id, status=status, schedule_seq=outcome.server_seq)
