from __future__ import annotations

from fastapi import Request

from medvital.core.module_spec import ModuleRegistry
from medvital.db.repository import ObservationRepository, ScheduleRepository


def get_repository(request: Request) -> ObservationRepository:
    return request.app.state.repository


def get_registry(request: Request) -> ModuleRegistry:
    return request.app.state.registry


def get_schedule_repository(request: Request) -> ScheduleRepository:
    return request.app.state.repository
