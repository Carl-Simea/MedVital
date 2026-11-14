"""Authorization helpers used at the API boundary (D-029, D-032).

Routes resolve scope here and hand processing code either plain filters or an ``authorize``
callable for write paths. Processing code never sees a principal.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException

from medvital.authz import (
    Permission,
    Principal,
    can_access_mission,
    can_access_subject,
    is_station,
    observation_write_problem,
    visible_subjects,
)
from medvital.core.schema import HealthObservation
from medvital.records_service import device_owner, list_missions

Authorizer = Callable[[HealthObservation], str | None]


def crews(repo) -> dict[str, list[str]]:
    return {m.mission_id: list(m.crew) for m in list_missions(repo)}


def need(principal: Principal, permission: Permission) -> None:
    if not principal.can(permission):
        raise HTTPException(status_code=403, detail=f"missing permission {permission.value}")


def need_station(principal: Principal, what: str) -> None:
    if not is_station(principal):
        raise HTTPException(status_code=403, detail=f"{what} is restricted to the local station service")


def need_subject(principal: Principal, repo, subject_id: str) -> None:
    if not can_access_subject(principal, subject_id, crews(repo)):
        raise HTTPException(status_code=403, detail="subject is outside this principal's scope")


def need_mission(principal: Principal, mission_id: str) -> None:
    if not can_access_mission(principal, mission_id):
        raise HTTPException(status_code=403, detail="mission is outside this principal's scope")


def need_subject_filter(principal: Principal, repo, subject_id: str | None) -> None:
    """Restricted principals must name a subject, and it must be in scope (no unscoped listing)."""
    allowed = visible_subjects(principal, crews(repo))
    if allowed is not None and (subject_id is None or subject_id not in allowed):
        raise HTTPException(status_code=403, detail="subject_id is required and must be within scope")


def write_authorizer(principal: Principal, repo) -> Authorizer | None:
    """Per-observation write check, or None for the trusted local station."""
    if is_station(principal):
        return None
    need(principal, Permission.WRITE_OBSERVATIONS)
    mission_crews = crews(repo)
    owners: dict[str, str | None] = {}

    def authorize(o: HealthObservation) -> str | None:
        owner = None
        if o.device_id is not None:
            if o.device_id not in owners:
                owners[o.device_id] = device_owner(repo, o.device_id)
            owner = owners[o.device_id]
        return observation_write_problem(principal, o.subject_id, o.device_id, mission_crews, owner)

    return authorize
