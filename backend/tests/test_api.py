from uuid import uuid4

from conftest import make_obs


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
