"""Authorization policy (Auth0 preparation, D-029). Pure functions; no I/O, no token handling.

Roles map to permissions; a separate *scope* check decides which subjects/missions a principal may
see. Data-processing code never sees a principal: routes resolve the scope first and pass plain
filters down (authorization stays separate from processing).

Modes (``Settings.auth_mode``):
* ``local`` — trusted station LAN (default). Every request acts as the ``local_station`` principal so
  local monitoring never depends on internet authentication.
* ``jwt`` — Auth0 access tokens. **Not implemented**: verifying RS256 tokens against Auth0's JWKS
  needs a JWT library (e.g. PyJWT[crypto]) that has not been approved (CLAUDE.md rule 7). Starting
  the API in this mode fails loudly instead of running unauthenticated.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    ASTRONAUT = "astronaut"
    SPACECRAFT_OPERATOR = "spacecraft_operator"
    GROUND_CONTROL = "ground_control"
    FLIGHT_SURGEON = "flight_surgeon"
    LOCAL_STATION = "local_station"  # trusted gateway process on the station LAN


class Permission(StrEnum):
    READ_OBSERVATIONS = "read:observations"
    WRITE_OBSERVATIONS = "write:observations"
    READ_ANALYSIS = "read:analysis"
    WRITE_RECORDS = "write:records"  # missions, schedules, references, environmental events
    READ_RECORDS = "read:records"
    EVALUATE_RULES = "evaluate:rules"
    ISSUE_RETURN_NOW = "issue:return_now"
    UPDATE_COMMAND = "update:command"
    READ_COMMANDS = "read:commands"
    WRITE_AI_EXPLANATION = "write:ai_explanation"
    READ_AUDIT = "read:audit"
    SYNC = "sync"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ASTRONAUT: frozenset(
        {
            Permission.READ_OBSERVATIONS,
            Permission.WRITE_OBSERVATIONS,
            Permission.READ_ANALYSIS,
            Permission.READ_RECORDS,
            Permission.READ_COMMANDS,
            Permission.UPDATE_COMMAND,
            # Own-device outbox sync: every pushed item is scope- and device-checked, every pull is
            # restricted to the astronaut's own subject (D-032). Record replication is station-only.
            Permission.SYNC,
        }
    ),
    Role.SPACECRAFT_OPERATOR: frozenset(
        {
            Permission.READ_OBSERVATIONS,
            Permission.WRITE_OBSERVATIONS,
            Permission.READ_ANALYSIS,
            Permission.READ_RECORDS,
            Permission.WRITE_RECORDS,
            Permission.EVALUATE_RULES,
            Permission.READ_COMMANDS,
            Permission.UPDATE_COMMAND,
            Permission.SYNC,
            Permission.READ_AUDIT,
        }
    ),
    Role.GROUND_CONTROL: frozenset(
        {
            Permission.READ_OBSERVATIONS,
            Permission.READ_ANALYSIS,
            Permission.READ_RECORDS,
            Permission.WRITE_RECORDS,
            Permission.EVALUATE_RULES,
            Permission.ISSUE_RETURN_NOW,
            Permission.UPDATE_COMMAND,
            Permission.READ_COMMANDS,
            Permission.WRITE_AI_EXPLANATION,
            Permission.READ_AUDIT,
            Permission.SYNC,
        }
    ),
    Role.FLIGHT_SURGEON: frozenset(
        {
            Permission.READ_OBSERVATIONS,
            Permission.READ_ANALYSIS,
            Permission.READ_RECORDS,
            Permission.ISSUE_RETURN_NOW,
            Permission.UPDATE_COMMAND,
            Permission.READ_COMMANDS,
            Permission.WRITE_AI_EXPLANATION,
        }
    ),
    Role.LOCAL_STATION: frozenset(Permission),
}


@dataclass(frozen=True)
class Principal:
    principal_id: str
    roles: frozenset[Role]
    subject_id: str | None = None  # an astronaut's own subject id
    missions: frozenset[str] = field(default_factory=frozenset)  # assigned missions
    human: bool = True

    def can(self, permission: Permission) -> bool:
        return any(permission in ROLE_PERMISSIONS[r] for r in self.roles)


LOCAL_STATION = Principal(principal_id="local-station", roles=frozenset({Role.LOCAL_STATION}), human=False)


class AuthorizationError(PermissionError):
    pass


def require(principal: Principal, permission: Permission) -> None:
    if not principal.can(permission):
        raise AuthorizationError(f"{principal.principal_id} lacks permission {permission.value}")


def visible_subjects(principal: Principal, mission_crews: dict[str, Iterable[str]]) -> set[str] | None:
    """Subjects this principal may see; ``None`` means unrestricted (local station only)."""
    if Role.LOCAL_STATION in principal.roles:
        return None
    subjects: set[str] = set()
    if Role.ASTRONAUT in principal.roles and principal.subject_id:
        subjects.add(principal.subject_id)
    if principal.roles & {Role.SPACECRAFT_OPERATOR, Role.GROUND_CONTROL, Role.FLIGHT_SURGEON}:
        for mission in principal.missions:
            subjects.update(mission_crews.get(mission, ()))
    return subjects


def can_access_subject(
    principal: Principal, subject_id: str, mission_crews: dict[str, Iterable[str]]
) -> bool:
    allowed = visible_subjects(principal, mission_crews)
    return allowed is None or subject_id in allowed


def can_access_mission(principal: Principal, mission_id: str) -> bool:
    if Role.LOCAL_STATION in principal.roles:
        return True
    return mission_id in principal.missions


def may_issue_return_now(principal: Principal, mission_id: str, issuer_principal_id: str) -> bool:
    """Human, permitted, assigned to the mission, and issuing in their own name (local station LAN console
    is trusted to record the human issuer it names)."""
    if Role.LOCAL_STATION in principal.roles:
        return True
    return (
        principal.human
        and principal.can(Permission.ISSUE_RETURN_NOW)
        and can_access_mission(principal, mission_id)
        and principal.principal_id == issuer_principal_id
    )


def is_station(principal: Principal) -> bool:
    return Role.LOCAL_STATION in principal.roles


def observation_write_problem(
    principal: Principal,
    subject_id: str,
    device_id: str | None,
    mission_crews: dict[str, Iterable[str]],
    device_owner: str | None,
) -> str | None:
    """Why ``principal`` may not write this observation, or None if allowed (D-032).

    Client-supplied identifiers never override authenticated ownership: the subject must be within
    the principal's scope (astronauts: only themselves), and a supplied ``device_id`` must currently
    be assigned to that same subject. The local station principal is trusted (station LAN).
    """
    if is_station(principal):
        return None
    if not principal.can(Permission.WRITE_OBSERVATIONS):
        return f"{principal.principal_id} lacks permission {Permission.WRITE_OBSERVATIONS.value}"
    if not can_access_subject(principal, subject_id, mission_crews):
        return f"subject {subject_id!r} is outside the scope of {principal.principal_id}"
    if device_id is not None and device_owner != subject_id:
        return f"device {device_id!r} is not assigned to subject {subject_id!r}"
    return None
