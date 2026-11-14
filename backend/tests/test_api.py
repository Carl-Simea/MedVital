from fastapi.testclient import TestClient

from medvital.db.repository import InMemoryObservationRepository
from medvital.main import create_app
from tests.conftest import make_obs

START = "2030-01-01T00:00:00Z"


def client() -> TestClient:
    return TestClient(create_app(repo=InMemoryObservationRepository()))


def test_health():
    body = client().get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["observation_schema_version"] == 1


def test_modules_endpoint_lists_four_modules_with_metrics():
    body = client().get("/api/v1/modules").json()
    assert {m["id"] for m in body} == {"radiation", "bone", "cardiovascular", "behavioral"}
    derived = [mt for m in body for mt in m["metrics"] if mt["derived"]]
    assert derived and all(mt["allowed_origins"] == ["modeled"] for mt in derived)


def test_profiles_are_all_marked_simulated():
    body = client().get("/api/v1/profiles").json()
    assert len(body) == 4
    assert all(p["is_simulated"] for p in body)


def test_simulate_does_not_store_by_default():
    c = client()
    r = c.post(
        "/api/v1/simulate",
        json={
            "profile_id": "SIM-001",
            "module": "radiation",
            "start": START,
            "days": 10,
            "seed": 1,
        },
    )
    assert r.status_code == 200
    origins = {o["provenance"]["origin"] for o in r.json()["observations"]}
    assert origins == {"simulated", "modeled"}
    assert r.json()["ingest"] is None
    assert c.get("/api/v1/observations").json()["observations"] == []


def test_simulate_with_store_then_query_and_summarise():
    c = client()
    r = c.post(
        "/api/v1/simulate",
        json={
            "profile_id": "SIM-001",
            "module": "cardiovascular",
            "start": START,
            "days": 10,
            "seed": 4,
            "store": True,
        },
    )
    assert r.status_code == 200
    assert r.json()["ingest"]["rejected"] == []
    stored = c.get("/api/v1/observations", params={"module": "cardiovascular"}).json()
    assert len(stored["observations"]) == len(r.json()["observations"])

    summary = c.get(
        "/api/v1/modules/cardiovascular/summary", params={"astronaut_id": "SIM-001"}
    ).json()
    assert "not a medical device" in summary["summary"]["notice"]
    keyed = {(m["metric"], m["origin"]) for m in summary["summary"]["metrics"]}
    assert ("heart_rate", "simulated") in keyed
    assert ("mean_arterial_pressure", "modeled") in keyed


def test_simulate_errors():
    c = client()
    body = {"profile_id": "NOPE", "module": "bone", "start": START, "days": 5, "seed": 1}
    assert c.post("/api/v1/simulate", json=body).status_code == 404
    assert (
        c.post("/api/v1/simulate", json={**body, "profile_id": "SIM-001", "days": 0}).status_code
        == 422
    )
    assert (
        c.post(
            "/api/v1/simulate",
            json={**body, "profile_id": "SIM-001", "start": "2030-01-01T00:00:00"},
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/api/v1/simulate", json={**body, "profile_id": "SIM-001", "module": "x"}
        ).status_code
        == 422
    )


def test_sync_push_partial_acceptance_and_idempotency():
    c = client()
    good = make_obs().model_dump(mode="json")
    bad = make_obs(unit="kg").model_dump(mode="json")
    first = c.post("/api/v1/sync/push", json={"device_id": "d1", "observations": [good, bad]})
    assert first.status_code == 200
    assert first.json()["accepted"] == [good["id"]]
    assert len(first.json()["rejected"]) == 1
    second = c.post("/api/v1/sync/push", json={"device_id": "d1", "observations": [good]})
    assert second.json()["duplicates"] == [good["id"]]


def test_sync_push_batch_limit_enforced():
    r = client().post("/api/v1/sync/push", json={"device_id": "d", "observations": [{}] * 501})
    assert r.status_code == 422


def test_sync_pull_pages_with_cursor():
    c = client()
    items = [make_obs(day=d).model_dump(mode="json") for d in range(5)]
    c.post("/api/v1/sync/push", json={"device_id": "d1", "observations": items})
    first = c.get("/api/v1/sync/pull", params={"cursor": 0, "limit": 3}).json()
    assert len(first["observations"]) == 3 and first["has_more"] is True
    second = c.get("/api/v1/sync/pull", params={"cursor": first["next_cursor"], "limit": 3}).json()
    assert len(second["observations"]) == 2 and second["has_more"] is False
    assert c.get("/api/v1/sync/pull", params={"cursor": -1}).status_code == 422
