"""M3: every write channel records its rejections; nothing is silently dropped."""

from uuid import uuid4

from conftest import make_obs


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
