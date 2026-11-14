"""Security regression tests for write (and scoped read) authorization at every API boundary (D-032).

Vulnerability fixed: a restricted principal (e.g. an astronaut) could submit observations under
another subject's or another device's identity through POST /observations, /sync/push and
/telemetry. Client-supplied subject, mission and device identifiers must never override
authenticated ownership; failures are per-item rejections that are logged, never silent.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from conftest import make_obs
from medvital.api.deps import get_principal
from medvital.authz import LOCAL_STATION, Principal, Role
from medvital.config import Settings
from medvital.core.records import DeviceAssignment, Mission
from medvital.core.schema import DataOrigin
from medvital.main import create_app

T = datetime(2026, 3, 1, 12, tzinfo=UTC)  # past: telemetry rejects future timestamps
ASTRO1 = Principal(
    "auth0|astro1", frozenset({Role.ASTRONAUT}), subject_id="SIM-T01", missions=frozenset({"SIM-M1"})
)
ASTRO2 = Principal(
    "auth0|astro2", frozenset({Role.ASTRONAUT}), subject_id="SIM-T02", missions=frozenset({"SIM-M1"})
)
OPERATOR = Principal("auth0|op1", frozenset({Role.SPACECRAFT_OPERATOR}), missions=frozenset({"SIM-M1"}))
GROUND = Principal("auth0|gc1", frozenset({Role.GROUND_CONTROL}), missions=frozenset({"SIM-M1"}))
SURGEON = Principal("auth0|fs1", frozenset({Role.FLIGHT_SURGEON}), missions=frozenset({"SIM-M1"}))


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
