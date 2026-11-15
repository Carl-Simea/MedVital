"""HTTP API, authorization policy, write authorization and the rejection audit log.

Merged from: test_api.py, test_authz_and_api.py, test_write_authorization.py, test_rejection_audit.py."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
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
from medvital.core.records import DeviceAssignment, EnvironmentalEvent, Mission
from medvital.core.schema import DataOrigin, Provenance
from medvital.main import create_app

# ---------------------------------------------------------------------- from test_api.py

def _j(obs):
    return obs.model_dump(mode="json")


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok" and r.json()["repository"] == "memory"


def test_modules_lists_four(client):
    data = client.get("/api/v1/modules").json()
    assert sorted(m["module"] for m in data) == ["behavioral", "bone", "cardiovascular", "radiation"]
    assert all(m["metrics"] for m in data)


def test_profiles_are_simulated(client):
    data = client.get("/api/v1/profiles").json()
    assert len(data) == 4 and all(p["data_origin"] == "simulated" for p in data)
    assert client.get("/api/v1/profiles/SIM-A01").status_code == 200
    assert client.get("/api/v1/profiles/NOPE").status_code == 404


def test_post_observations_accept_duplicate_reject(client):
    ok = make_obs()
    bad_unit = make_obs(unit="rad")
    r = client.post("/api/v1/observations", json={"observations": [_j(ok), _j(ok), _j(bad_unit)]})
    statuses = [x["status"] for x in r.json()["results"]]
    assert r.status_code == 200 and statuses == ["accepted", "duplicate", "rejected"]
    assert "canonical unit" in r.json()["results"][2]["error"]


def test_malformed_observation_is_422(client):
    body = _j(make_obs())
    del body["provenance"]
    assert client.post("/api/v1/observations", json={"observations": [body]}).status_code == 422


def test_simulate_persist_summary_roundtrip(client):
    r = client.post(
        "/api/v1/profiles/SIM-A01/simulate",
        json={"start": "2030-01-01T00:00:00Z", "days": 30, "seed": 1, "persist": True},
    )
    assert r.status_code == 200 and r.json()["persisted"] is True
    n = len(r.json()["observations"])
    stored = client.get("/api/v1/observations", params={"subject_id": "SIM-A01", "limit": 10000}).json()
    assert len(stored) == n
    for module in ("radiation", "bone", "cardiovascular", "behavioral"):
        s = client.get(f"/api/v1/modules/{module}/summary", params={"subject_id": "SIM-A01"}).json()
        assert s["module"] == module and s["observation_count"] > 0
        assert "Not a diagnosis" in s["notice"]
        assert all(d["data_origin"] == "modeled" and d["input_origin"] == "simulated" for d in s["derived_values"])


def test_simulate_not_persisted_by_default(client):
    client.post("/api/v1/profiles/SIM-A01/simulate", json={"start": "2030-01-01T00:00:00Z", "days": 3})
    assert client.get("/api/v1/observations").json() == []


def test_simulate_rejects_naive_start(client):
    r = client.post("/api/v1/profiles/SIM-A01/simulate", json={"start": "2030-01-01T00:00:00", "days": 3})
    assert r.status_code == 422


def test_summary_requires_subject(client):
    assert client.get("/api/v1/modules/bone/summary").status_code == 422


def test_unknown_module_404_or_422(client):
    assert client.get("/api/v1/modules/nope/summary", params={"subject_id": "x"}).status_code == 422


class TestSync:
    def _push(self, client, observations, client_id="dev-1"):
        body = {
            "client_id": client_id,
            "mutations": [{"mutation_id": str(uuid4()), "observation": _j(o)} for o in observations],
        }
        return client.post("/api/v1/sync/push", json=body)

    def test_push_is_idempotent(self, client):
        o = make_obs()
        first = self._push(client, [o]).json()
        second = self._push(client, [o]).json()
        assert first["results"][0]["status"] == "accepted"
        assert second["results"][0]["status"] == "duplicate"
        assert second["results"][0]["server_seq"] == first["results"][0]["server_seq"]
        assert second["server_cursor"] == 1

    def test_push_echoes_mutation_id(self, client):
        body = {
            "client_id": "dev-1",
            "mutations": [{"mutation_id": "11111111-1111-4111-8111-111111111111", "observation": _j(make_obs())}],
        }
        res = client.post("/api/v1/sync/push", json=body).json()["results"][0]
        assert res["mutation_id"] == "11111111-1111-4111-8111-111111111111"

    def test_push_conflict_rejected(self, client):
        i = uuid4()
        self._push(client, [make_obs(value=1.0, id=i)])
        res = self._push(client, [make_obs(value=2.0, id=i)]).json()["results"][0]
        assert res["status"] == "rejected" and "immutable" in res["error"]

    def test_push_partial_failure_does_not_block_batch(self, client):
        good, bad = make_obs(), make_obs(value=-1.0)
        statuses = [r["status"] for r in self._push(client, [bad, good]).json()["results"]]
        assert statuses == ["rejected", "accepted"]

    def test_pull_pagination_and_cursor(self, client):
        self._push(client, [make_obs(day=i) for i in range(5)])
        page1 = client.get("/api/v1/sync/pull", params={"cursor": 0, "limit": 2}).json()
        assert [c["server_seq"] for c in page1["changes"]] == [1, 2]
        assert page1["has_more"] is True and page1["next_cursor"] == 2
        page2 = client.get("/api/v1/sync/pull", params={"cursor": 2, "limit": 10}).json()
        assert [c["server_seq"] for c in page2["changes"]] == [3, 4, 5]
        assert page2["has_more"] is False and page2["next_cursor"] == 5
        page3 = client.get("/api/v1/sync/pull", params={"cursor": 5}).json()
        assert page3["changes"] == [] and page3["next_cursor"] == 5

    def test_pull_empty_store(self, client):
        r = client.get("/api/v1/sync/pull").json()
        assert r == {"changes": [], "next_cursor": 0, "has_more": False}

    def test_batch_limit(self, client):
        body = {
            "client_id": "dev-1",
            "mutations": [{"mutation_id": str(uuid4()), "observation": _j(make_obs())}] * 501,
        }
        assert client.post("/api/v1/sync/push", json=body).status_code == 422

    def test_push_invalid_client_id(self, client):
        assert self._push(client, [make_obs()], client_id="bad id!").status_code == 422


# ---------------------------------------------------------------------- from test_authz_and_api.py

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


# ---------------------------------------------------------------------- from test_write_authorization.py

ASTRO1 = Principal(
    "auth0|astro1", frozenset({Role.ASTRONAUT}), subject_id="SIM-T01", missions=frozenset({"SIM-M1"})
)
ASTRO2 = Principal(
    "auth0|astro2", frozenset({Role.ASTRONAUT}), subject_id="SIM-T02", missions=frozenset({"SIM-M1"})
)


def _mission(mid, crew):
    return Mission(
        mission_id=mid,
        name=mid,
        launch_at=T - timedelta(days=30),
        crew=crew,
        data_origin=DataOrigin.SIMULATED,
        created_at=T - timedelta(days=60),
    ).model_dump(mode="json")


def _assign(device, subject, mission="SIM-M1", by="local-station", at=T - timedelta(days=1)):
    return DeviceAssignment(
        assignment_id=uuid4(),
        device_id=device,
        subject_id=subject,
        mission_id=mission,
        assigned_by=by,
        assigned_at=at,
    ).model_dump(mode="json")


@pytest.fixture
def env():
    app = create_app(Settings(repository="memory"))
    client = TestClient(app)
    client.post("/api/v1/missions", json=_mission("SIM-M1", ["SIM-T01", "SIM-T02"]))
    client.post("/api/v1/missions", json=_mission("SIM-M2", ["SIM-T09"]))
    for dev, subj, mis in (
        ("W1", "SIM-T01", "SIM-M1"),
        ("W2", "SIM-T02", "SIM-M1"),
        ("W9", "SIM-T09", "SIM-M2"),
    ):
        assert (
            client.post("/api/v1/devices/assignments", json=_assign(dev, subj, mis)).json()["status"]
            == "accepted"
        )

    def as_(who):
        app.dependency_overrides[get_principal] = lambda: who

    return SimpleNamespace(app=app, client=client, as_=as_, repo=app.state.repository)


def obs(subject="SIM-T01", device=None, **kw):
    o = make_obs("behavioral.sleep_duration", 7.0, subject_id=subject, **kw)
    return o.model_copy(update={"device_id": device}) if device else o


def post(env, observations):
    r = env.client.post(
        "/api/v1/observations", json={"observations": [o.model_dump(mode="json") for o in observations]}
    )
    return r


def statuses(r):
    return [x["status"] for x in r.json()["results"]]


def stored(env, o):
    return env.repo.get(o.id) is not None


def rejection_reasons(env):
    return [r.reason for r in env.repo.list_rejections(1000)]


# --------------------------------------------------------------------------- POST /observations


def test_astronaut_can_write_own_record(env):
    env.as_(ASTRO1)
    own, with_device = obs(), obs(device="W1")
    assert statuses(post(env, [own, with_device])) == ["accepted", "accepted"]


def test_astronaut_cannot_write_for_another_astronaut(env):
    env.as_(ASTRO1)
    foreign = obs("SIM-T02")
    r = post(env, [foreign])
    assert statuses(r) == ["rejected"] and "outside the scope" in r.json()["results"][0]["error"]
    assert not stored(env, foreign)
    assert any(x.startswith("authorization:") for x in rejection_reasons(env))  # logged, not silent


def test_astronaut_cannot_use_another_device_identity(env):
    env.as_(ASTRO1)
    for device in ("W2", "W9", "UNREGISTERED"):  # other astronaut's, other mission's, unknown
        o = obs(device=device)
        r = post(env, [o])
        assert statuses(r) == ["rejected"] and "not assigned" in r.json()["results"][0]["error"]
        assert not stored(env, o)


def test_mixed_batch_is_decided_per_item(env):
    env.as_(ASTRO1)
    good, bad = obs(), obs("SIM-T02")
    assert statuses(post(env, [good, bad])) == ["accepted", "rejected"]
    assert stored(env, good) and not stored(env, bad)


def test_device_reassignment_moves_ownership(env):
    env.as_(OPERATOR)
    reassign = _assign("W1", "SIM-T02", by="auth0|op1", at=T)
    assert env.client.post("/api/v1/devices/assignments", json=reassign).json()["status"] == "accepted"
    env.as_(ASTRO1)
    assert statuses(post(env, [obs(device="W1")])) == ["rejected"]
    env.as_(ASTRO2)
    assert statuses(post(env, [obs("SIM-T02", device="W1")])) == ["accepted"]


def test_operator_scope(env):
    env.as_(OPERATOR)
    assert statuses(post(env, [obs("SIM-T02", device="W2")])) == ["accepted"]
    assert statuses(post(env, [obs("SIM-T09")])) == ["rejected"]  # other mission's crew
    assert statuses(post(env, [obs("SIM-T01", device="W2")])) == ["rejected"]  # device of another subject


def test_roles_without_write_permission_are_refused(env):
    for who in (GROUND, SURGEON):
        env.as_(who)
        assert post(env, [obs()]).status_code == 403


# --------------------------------------------------------------------------- POST /sync/push


def test_sync_push_enforces_the_same_rules(env):
    env.as_(ASTRO1)
    own, foreign, spoofed = obs(), obs("SIM-T02"), obs(device="W2")
    body = {
        "client_id": "astro1-phone",
        "mutations": [
            {"mutation_id": str(uuid4()), "observation": o.model_dump(mode="json")}
            for o in (own, foreign, spoofed)
        ],
    }
    r = env.client.post("/api/v1/sync/push", json=body).json()
    assert [x["status"] for x in r["results"]] == ["accepted", "rejected", "rejected"]
    assert stored(env, own) and not stored(env, foreign) and not stored(env, spoofed)


# --------------------------------------------------------------------------- POST /telemetry


def _event(crew, device, eid):
    return {
        "event_id": eid,
        "device_id": device,
        "crew_id": crew,
        "timestamp": T.isoformat(),
        "domain": "cardiovascular",
        "indicator": "heart_rate",
        "value": 60,
        "unit": "bpm",
        "source": "simulated_sensor",
        "quality": "valid",
        "synthetic": True,
        "generator_version": "t",
        "seed": 1,
    }


def test_telemetry_enforces_subject_and_device_ownership(env):
    env.as_(ASTRO1)
    events = [_event("SIM-T01", "W1", "E1"), _event("SIM-T02", "W2", "E2"), _event("SIM-T01", "W2", "E3")]
    r = env.client.post("/api/v1/telemetry", json={"events": events}).json()
    assert [x["status"] for x in r["results"]] == ["accepted", "rejected", "rejected"]
    assert r["accepted"] == 1 and all("authorization" in x["error"] for x in r["results"][1:])


# --------------------------------------------------------------------------- missions, devices, schedules, simulation


def test_astronaut_cannot_assign_themselves_to_missions_or_devices(env):
    env.as_(ASTRO1)
    assert env.client.post("/api/v1/missions", json=_mission("SIM-M3", ["SIM-T01"])).status_code == 403
    assert (
        env.client.post(
            "/api/v1/devices/assignments", json=_assign("W5", "SIM-T01", by="auth0|astro1")
        ).status_code
        == 403
    )


def test_operators_cannot_create_or_assign_outside_their_missions(env):
    env.as_(OPERATOR)
    assert env.client.post("/api/v1/missions", json=_mission("SIM-M3", ["SIM-T01"])).status_code == 403
    assert (
        env.client.post(
            "/api/v1/devices/assignments", json=_assign("W5", "SIM-T09", "SIM-M2", by="auth0|op1")
        ).status_code
        == 403
    )
    assert (
        env.client.post(
            "/api/v1/devices/assignments", json=_assign("W5", "SIM-T01", by="auth0|someone")
        ).status_code
        == 403
    )
    r = env.client.post("/api/v1/devices/assignments", json=_assign("W5", "SIM-T09", by="auth0|op1")).json()
    assert r["status"] == "rejected" and "not in mission" in r["error"]  # subject not in this mission's crew


def test_schedules_are_scoped(env):
    from medvital.core.schedule import Anchor, MeasurementSchedule, ScheduleBasis, SingleTimepoint

    def sched(subject):
        return MeasurementSchedule(
            id=uuid4(),
            subject_id=subject,
            metric="behavioral.sleep_duration",
            method="actigraphy",
            events=[SingleTimepoint(anchor=Anchor.LAUNCH, offset_days=1)],
            basis=ScheduleBasis.SIMULATED,
            source="pytest",
            created_at=T,
        ).model_dump(mode="json")

    env.as_(ASTRO1)
    assert env.client.post("/api/v1/schedules", json=sched("SIM-T01")).status_code == 403  # no write:records
    env.as_(OPERATOR)
    assert env.client.post("/api/v1/schedules", json=sched("SIM-T09")).status_code == 403
    s = sched("SIM-T02")
    assert env.client.post("/api/v1/schedules", json=s).json()["status"] == "accepted"
    env.as_(ASTRO1)
    assert env.client.get("/api/v1/schedules").status_code == 403
    assert env.client.get(f"/api/v1/schedules/{s['id']}").status_code == 403  # T02's schedule


def test_simulation_persist_is_station_only(env):
    env.as_(ASTRO1)
    body = {"start": T.isoformat(), "days": 2, "seed": 1, "persist": True}
    profile = env.client.get("/api/v1/profiles").json()[0]["profile_id"]
    assert env.client.post(f"/api/v1/profiles/{profile}/simulate", json=body).status_code == 403
    assert (
        env.client.post(f"/api/v1/profiles/{profile}/simulate", json={**body, "persist": False}).status_code
        == 200
    )


# --------------------------------------------------------------------------- scoped reads and station-only endpoints


def test_reads_are_scoped(env):
    env.as_(LOCAL_STATION)
    post(env, [obs("SIM-T02", device="W2")])
    env.as_(ASTRO1)
    assert env.client.get("/api/v1/sync/pull").status_code == 403
    assert env.client.get("/api/v1/sync/pull", params={"subject_id": "SIM-T02"}).status_code == 403
    assert env.client.get("/api/v1/sync/pull", params={"subject_id": "SIM-T01"}).status_code == 200
    assert env.client.get("/api/v1/telemetry/rejections").status_code == 403
    assert all(d["crew_id"] == "SIM-T01" for d in env.client.get("/api/v1/live").json()["devices"])
    for path in ("/api/v1/sync/documents/pull",):
        assert env.client.get(path).status_code == 403
    assert (
        env.client.post("/api/v1/sync/documents/push", json={"client_id": "x", "documents": []}).status_code
        == 403
    )


def test_ai_explanation_requester_and_citations_are_scoped(env):
    env.as_(LOCAL_STATION)
    other = obs("SIM-T09")
    post(env, [other])
    env.as_(SURGEON)
    base = {
        "explanation_id": str(uuid4()),
        "provider": "gemini",
        "model": "t",
        "created_at": T.isoformat(),
        "question": "q",
        "summary": "s",
        "evidence": ["e"],
        "input_data_classes": ["simulated"],
        "cited_observation_ids": [str(other.id)],
    }
    assert (
        env.client.post("/api/v1/ai/explanations", json={**base, "requested_by": "auth0|other"}).status_code
        == 403
    )
    assert (
        env.client.post("/api/v1/ai/explanations", json={**base, "requested_by": "auth0|fs1"}).status_code
        == 403
    )


# --------------------------------------------------------------------------- modes


def test_local_mode_station_is_trusted_without_internet_auth(env):
    env.app.dependency_overrides.clear()  # real dependency: local mode -> LOCAL_STATION
    unregistered = obs("SIM-T77", device="BENCH-1")
    assert statuses(post(env, [unregistered])) == ["accepted"]


def test_authenticated_mode_rejects_requests_and_refuses_to_start():
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=Settings(auth_mode="jwt"))))
    with pytest.raises(HTTPException) as exc:
        get_principal(request)
    assert exc.value.status_code == 401
    with pytest.raises(RuntimeError, match="not implemented"):
        create_app(Settings(repository="memory", auth_mode="jwt"))


# ---------------------------------------------------------------------- from test_rejection_audit.py

def _post(client, obs):
    return client.post(
        "/api/v1/observations", json={"observations": [o.model_dump(mode="json") for o in obs]}
    )


def _log(client):
    return client.get("/api/v1/telemetry/rejections").json()


def test_api_semantic_rejection_is_logged(client):
    bad = make_obs("behavioral.sleep_duration", 7.0, unit="min")
    assert _post(client, [bad]).json()["results"][0]["status"] == "rejected"
    (entry,) = _log(client)
    assert entry["source"] == "api" and "canonical unit" in entry["reason"]
    assert entry["payload"]["observation"]["id"] == str(bad.id)


def test_api_conflict_is_logged_and_original_kept(client):
    i = uuid4()
    _post(client, [make_obs(value=1.0, id=i)])
    assert _post(client, [make_obs(value=2.0, id=i)]).json()["results"][0]["status"] == "rejected"
    (entry,) = _log(client)
    assert "immutable" in entry["reason"] and entry["payload"]["observation"]["value"] == 2.0
    assert client.get("/api/v1/observations", params={"subject_id": "SIM-T01"}).json()[0]["value"] == 1.0


def test_sync_rejection_records_client_and_mutation(client):
    bad = make_obs("behavioral.sleep_duration", -1.0)  # negative duration: physically implausible
    mutation_id = str(uuid4())
    r = client.post(
        "/api/v1/sync/push",
        json={
            "client_id": "station-A",
            "mutations": [{"mutation_id": mutation_id, "observation": bad.model_dump(mode="json")}],
        },
    ).json()
    assert r["results"][0]["status"] == "rejected"
    (entry,) = _log(client)
    assert entry["source"] == "sync"
    assert entry["payload"]["client_id"] == "station-A" and entry["payload"]["mutation_id"] == mutation_id


def test_accepted_and_duplicate_writes_are_not_logged(client):
    o = make_obs()
    _post(client, [o])
    _post(client, [o])
    assert _log(client) == []
