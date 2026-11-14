"""Authorization policy (Auth0 preparation, D-029) and the records/analysis/rules/command API."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import make_obs, measured_provenance
from medvital.api.deps import get_principal
from medvital.authz import (
    LOCAL_STATION,
    Permission,
    Principal,
    Role,
    can_access_subject,
    may_issue_return_now,
    visible_subjects,
)
from medvital.config import Settings
from medvital.core.records import EnvironmentalEvent, Mission
from medvital.core.schema import DataOrigin, Provenance
from medvital.main import create_app

T = datetime(2026, 3, 1, 12, tzinfo=UTC)  # in the past: telemetry/rules use real "now"
CREWS = {"SIM-M1": ["SIM-T01", "SIM-T02"], "SIM-M2": ["SIM-T09"]}


def principal(role, pid="auth0|p1", subject=None, missions=()):
    return Principal(
        principal_id=pid, roles=frozenset({role}), subject_id=subject, missions=frozenset(missions)
    )


ASTRONAUT = principal(Role.ASTRONAUT, "auth0|astro1", subject="SIM-T01", missions=["SIM-M1"])
OPERATOR = principal(Role.SPACECRAFT_OPERATOR, "auth0|op1", missions=["SIM-M1"])
GROUND = principal(Role.GROUND_CONTROL, "auth0|gc1", missions=["SIM-M1"])
SURGEON = principal(Role.FLIGHT_SURGEON, "auth0|fs1", missions=["SIM-M1"])


# --------------------------------------------------------------------------- policy


def test_scope_matrix():
    assert visible_subjects(ASTRONAUT, CREWS) == {"SIM-T01"}
    assert visible_subjects(OPERATOR, CREWS) == {"SIM-T01", "SIM-T02"}
    assert visible_subjects(GROUND, CREWS) == {"SIM-T01", "SIM-T02"}
    assert visible_subjects(LOCAL_STATION, CREWS) is None
    assert not can_access_subject(ASTRONAUT, "SIM-T02", CREWS)
    assert not can_access_subject(OPERATOR, "SIM-T09", CREWS)


def test_permission_matrix():
    assert not ASTRONAUT.can(Permission.ISSUE_RETURN_NOW) and not OPERATOR.can(Permission.ISSUE_RETURN_NOW)
    assert SURGEON.can(Permission.ISSUE_RETURN_NOW) and GROUND.can(Permission.ISSUE_RETURN_NOW)
    assert not ASTRONAUT.can(Permission.READ_AUDIT) and not SURGEON.can(Permission.WRITE_RECORDS)


def test_return_now_issuer_rules():
    assert may_issue_return_now(SURGEON, "SIM-M1", "auth0|fs1")
    assert not may_issue_return_now(SURGEON, "SIM-M1", "auth0|someone-else")  # own name only
    assert not may_issue_return_now(SURGEON, "SIM-M2", "auth0|fs1")  # assigned missions only
    assert not may_issue_return_now(ASTRONAUT, "SIM-M1", "auth0|astro1")
    bot = Principal(
        "svc|gemini", frozenset({Role.FLIGHT_SURGEON}), missions=frozenset({"SIM-M1"}), human=False
    )
    assert not may_issue_return_now(bot, "SIM-M1", "svc|gemini")


def test_jwt_mode_refuses_to_start_unauthenticated():
    with pytest.raises(RuntimeError, match="not implemented"):
        create_app(Settings(repository="memory", auth_mode="jwt"))


# --------------------------------------------------------------------------- API helpers


def mission_body(mid="SIM-M1", crew=("SIM-T01", "SIM-T02")):
    return Mission(
        mission_id=mid,
        name="sim",
        launch_at=T - timedelta(days=30),
        crew=list(crew),
        data_origin=DataOrigin.SIMULATED,
        created_at=T - timedelta(days=60),
    ).model_dump(mode="json")


def command_body(issuer_id="auth0|fs1", mission="SIM-M1"):
    return {
        "command_id": str(uuid4()),
        "mission_id": mission,
        "issued_at": T.isoformat(),
        "issuer": {"principal_id": issuer_id, "display_name": "Flight Surgeon", "role": "flight_surgeon"},
        "reason": "Simulated drill.",
        "mission_context": "Simulated mission.",
    }


@pytest.fixture
def station():
    app = create_app(Settings(repository="memory"))
    client = TestClient(app)
    client.post("/api/v1/missions", json=mission_body())
    client.post("/api/v1/missions", json=mission_body("SIM-M2", ("SIM-T09",)))
    obs = [
        make_obs("behavioral.sleep_duration", v, day=i, subject_id=s)
        for s in ("SIM-T01", "SIM-T02")
        for i, v in enumerate([6.0, 7.0])
    ]
    client.post("/api/v1/observations", json={"observations": [o.model_dump(mode="json") for o in obs]})
    return app, client


def as_(app, who):
    app.dependency_overrides[get_principal] = lambda: who


# --------------------------------------------------------------------------- scoped API


def test_astronaut_sees_only_own_records(station):
    app, client = station
    as_(app, ASTRONAUT)
    assert client.get("/api/v1/observations").status_code == 403  # must name a subject
    assert client.get("/api/v1/observations", params={"subject_id": "SIM-T02"}).status_code == 403
    assert len(client.get("/api/v1/observations", params={"subject_id": "SIM-T01"}).json()) == 2
    assert (
        client.get("/api/v1/modules/behavioral/summary", params={"subject_id": "SIM-T02"}).status_code == 403
    )
    assert client.post("/api/v1/analysis", json={"subject_id": "SIM-T02"}).status_code == 403
    assert client.get("/api/v1/audit/writes").status_code == 403
    assert [m["mission_id"] for m in client.get("/api/v1/missions").json()] == ["SIM-M1"]


def test_return_now_api_is_human_scoped(station):
    app, client = station
    as_(app, ASTRONAUT)
    assert client.post("/api/v1/commands/return-now", json=command_body("auth0|astro1")).status_code == 403
    as_(app, SURGEON)
    assert client.post("/api/v1/commands/return-now", json=command_body("auth0|other")).status_code == 403
    assert client.post("/api/v1/commands/return-now", json=command_body(mission="SIM-M2")).status_code == 403
    body = command_body()
    assert client.post("/api/v1/commands/return-now", json=body).json()["status"] == "accepted"
    state = client.get(f"/api/v1/commands/{body['command_id']}").json()
    assert state["status"] == "issued" and state["command"]["issuer"]["issuer_type"] == "human"
    ack = {"status": "acknowledged", "actor": body["issuer"], "at": (T + timedelta(minutes=1)).isoformat()}
    assert (
        client.post(f"/api/v1/commands/{body['command_id']}/status", json=ack).json()["status"] == "accepted"
    )
    as_(app, OPERATOR)  # operator may acknowledge only in their own name
    other = {**ack, "status": "in_progress", "at": (T + timedelta(minutes=2)).isoformat()}
    assert client.post(f"/api/v1/commands/{body['command_id']}/status", json=other).status_code == 403


def test_ground_control_analysis_within_mission(station):
    app, client = station
    as_(app, GROUND)
    r = client.post("/api/v1/analysis", json={"subject_id": "SIM-T02", "metric": "behavioral.sleep_duration"})
    assert r.status_code == 200 and r.json()["series"][0]["key"]["subject_id"] == "SIM-T02"
    assert client.post("/api/v1/analysis", json={"subject_id": "SIM-T09"}).status_code == 403


# --------------------------------------------------------------------------- local-mode end-to-end


def test_records_endpoints_end_to_end(station):
    _, client = station
    ref = {
        "reference_id": "REF-TEST-0001",
        "citation": "Test citation (fixture).",
        "source_identifier": "doi:10.0/test",
        "verification": "unverified",
        "quantity": "example",
        "metric": "bone.areal_bmd",
        "unit": "g/cm2",
        "statistic": "mean",
        "value": 1.0,
        "population": {"description": "fixture", "species": "Homo sapiens"},
        "limitations": "Test fixture only.",
        "retrieved_at": T.isoformat(),
    }
    assert client.post("/api/v1/references", json=ref).json()["status"] == "accepted"
    assert client.get("/api/v1/references/REF-TEST-0001").json()["verification"] == "unverified"
    assert client.get("/api/v1/references/REF-NOPE-1").status_code == 404

    ev = EnvironmentalEvent(
        event_id=EnvironmentalEvent.make_id("NASA DONKI", "TEST-SEP-1", None),
        source_system="NASA DONKI",
        event_type="SEP",
        source_event_id="TEST-SEP-1",
        start_time=T,
        provenance=Provenance(data_origin=DataOrigin.MEASURED, source="NASA DONKI", source_ref="test://sep"),
    )
    assert (
        client.post("/api/v1/environment/events", json=ev.model_dump(mode="json")).json()["status"]
        == "accepted"
    )
    assert [e["source_event_id"] for e in client.get("/api/v1/environment/events").json()] == ["TEST-SEP-1"]

    findings = client.post(
        "/api/v1/rules/evaluate", json={"now": (T + timedelta(hours=1)).isoformat(), "persist": True}
    ).json()
    assert "space_weather_notice" in {f["category"] for f in findings}
    assert all(f["clinical"] is False for f in findings)
    assert len(client.get("/api/v1/rules/findings").json()) == len(findings)

    sim = client.get("/api/v1/observations", params={"subject_id": "SIM-T01"}).json()[0]
    expl = {
        "explanation_id": str(uuid4()),
        "provider": "gemini",
        "model": "test",
        "created_at": T.isoformat(),
        "requested_by": "auth0|gc1",
        "question": "q",
        "summary": "s",
        "evidence": ["e"],
        "cited_observation_ids": [sim["id"]],
        "input_data_classes": ["simulated"],
    }
    assert client.post("/api/v1/ai/explanations", json=expl).json()["status"] == "accepted"
    private = make_obs(provenance=measured_provenance(), subject_id="SIM-T01")
    client.post("/api/v1/observations", json={"observations": [private.model_dump(mode="json")]})
    bad = {**expl, "explanation_id": str(uuid4()), "cited_observation_ids": [str(private.id)]}
    assert "D-022" in client.post("/api/v1/ai/explanations", json=bad).json()["error"]

    writes = client.get("/api/v1/audit/writes").json()
    assert {w["channel"] for w in writes} == {"api"} and len(writes) == 5
    assert client.get("/api/v1/audit/upstream-failures").json() == []
