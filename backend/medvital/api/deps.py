from __future__ import annotations

from fastapi import HTTPException, Request

from medvital.authz import LOCAL_STATION, Principal
from medvital.core.module_spec import ModuleRegistry
from medvital.db.repository import ObservationRepository, ScheduleRepository


def get_repository(request: Request) -> ObservationRepository:
    return request.app.state.repository


def get_registry(request: Request) -> ModuleRegistry:
    return request.app.state.registry


def get_schedule_repository(request: Request) -> ScheduleRepository:
    return request.app.state.repository


def get_principal(request: Request) -> Principal:
    """Resolve the caller. Local mode: the trusted station principal (D-029)."""
    mode = request.app.state.settings.auth_mode
    if mode == "local":
        return LOCAL_STATION
    raise HTTPException(status_code=401, detail=f"auth mode {mode!r} is not available")
