"""Station -> upstream delivery and the three-station (astronaut, spacecraft, ground) contracts.

Merged from: test_upstream.py, test_three_station.py."""

import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import make_obs, measured_provenance
from medvital.config import Settings
from medvital.core.records import (
    AIExplanation,
    CommandStatus,
    CommandStatusEvent,
    HumanIssuer,
    Mission,
    ReturnNowCommand,
)
from medvital.core.schema import DataOrigin
from medvital.db.repository import InMemoryObservationRepository
from medvital.db.sqlite import SqliteObservationRepository
from medvital.main import create_app
from medvital.records_service import command_state, issue_return_now, store_mission, transition_command
from medvital.registry import build_registry
from medvital.upstream import (
    HttpUpstreamTransport,
    UpstreamBatchInvalid,
    UpstreamRefused,
    UpstreamUnavailable,
    mutation_for,
    pull_documents,
    push_documents_upstream,
    push_upstream,
)

# ---------------------------------------------------------------------- from test_upstream.py

DEST = "spacecraft"


class GatewayTransport:
    """Pushes into a real second MEDVITAL app (the upstream station) through its HTTP contract."""

    def __init__(self) -> None:
        self.upstream_repo = InMemoryObservationRepository()
        self.client = TestClient(create_app(Settings(repository="memory"), repository=self.upstream_repo))
        self.online = True
        self.calls = 0

    def push(self, client_id, mutations):
        self.calls += 1
        if not self.online:
            raise UpstreamUnavailable("simulated link down")
        r = self.client.post("/api/v1/sync/push", json={"client_id": client_id, "mutations": mutations})
        if r.status_code == 422:
            raise UpstreamBatchInvalid("422")
        if r.status_code >= 500:
            raise UpstreamUnavailable(str(r.status_code))
        if r.status_code >= 400:
            raise UpstreamRefused(str(r.status_code))
        return r.json()["results"]


def _fill(repo, n, start_day=0):
    obs = [make_obs("behavioral.sleep_duration", 7.0, day=start_day + i) for i in range(n)]
    for o in obs:
        repo.add(o)
    return obs


@pytest.fixture(params=["memory", "sqlite"])
def station(request, tmp_path):
    if request.param == "memory":
        yield InMemoryObservationRepository()
    else:
        r = SqliteObservationRepository(tmp_path / "station.db")
        yield r
        r.close()


def test_delivery_is_complete_and_then_idle(station):
    t = GatewayTransport()
    _fill(station, 7)
    rep = push_upstream(station, t, destination=DEST, client_id="astronaut-1", batch_size=3)
    assert (rep.status, rep.sent, rep.accepted, rep.cursor_after) == ("complete", 7, 7, 7)
    assert t.upstream_repo.head_seq() == 7
    again = push_upstream(station, t, destination=DEST, client_id="astronaut-1")
    assert again.sent == 0 and again.status == "complete"


def test_link_down_keeps_local_monitoring_and_delivers_exactly_once_after(station):
    """Situation A: upstream unreachable, local network/gateway fine."""
    t = GatewayTransport()
    _fill(station, 3)
    push_upstream(station, t, destination=DEST, client_id="a1")
    t.online = False
    _fill(station, 4, start_day=10)  # local writes continue during the outage
    down = push_upstream(station, t, destination=DEST, client_id="a1")
    assert down.status == "unavailable" and down.cursor_after == down.cursor_before == 3
    assert station.head_seq() == 7  # nothing lost locally
    t.online = True
    up = push_upstream(station, t, destination=DEST, client_id="a1")
    assert up.status == "complete" and up.accepted == 4 and up.duplicate == 0
    assert t.upstream_repo.head_seq() == 7


def test_total_interruption_with_restart_resumes_from_persisted_cursor(tmp_path):
    """Situation B: full outage and a station restart in between."""
    path = tmp_path / "station.db"
    t = GatewayTransport()
    s1 = SqliteObservationRepository(path)
    _fill(s1, 5)
    push_upstream(s1, t, destination=DEST, client_id="a1", batch_size=2, max_batches=1)  # 2 delivered
    t.online = False
    assert push_upstream(s1, t, destination=DEST, client_id="a1").status == "unavailable"
    s1.close()
    s2 = SqliteObservationRepository(path)  # restart
    assert s2.upstream_cursor(DEST) == 2
    t.online = True
    rep = push_upstream(s2, t, destination=DEST, client_id="a1")
    s2.close()
    assert rep.accepted == 3 and t.upstream_repo.head_seq() == 5


def test_retry_after_lost_response_is_duplicate_not_double(station):
    """Upstream stored the batch but the reply was lost: resend must not duplicate."""
    t = GatewayTransport()
    _fill(station, 2)
    mutations = [mutation_for(DEST, r) for r in station.changes_since(0)]
    t.client.post("/api/v1/sync/push", json={"client_id": "a1", "mutations": mutations})  # reply "lost"
    rep = push_upstream(station, t, destination=DEST, client_id="a1")
    assert rep.duplicate == 2 and rep.accepted == 0 and t.upstream_repo.head_seq() == 2


class FakeTransport:
    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.pushed = []

    def push(self, client_id, mutations):
        self.pushed.append(mutations)
        return self.behaviour(mutations)


def _ok(mutations, status="accepted"):
    return [{"observation_id": m["observation"]["id"], "status": status} for m in mutations]


def test_upstream_rejection_is_audited_and_skipped(station):
    obs = _fill(station, 3)
    bad_id = str(obs[1].id)

    def behaviour(mutations):
        return [
            {
                "observation_id": m["observation"]["id"],
                "status": "rejected",
                "error": "unknown metric upstream",
            }
            if m["observation"]["id"] == bad_id
            else {"observation_id": m["observation"]["id"], "status": "accepted"}
            for m in mutations
        ]

    rep = push_upstream(station, FakeTransport(behaviour), destination=DEST, client_id="a1")
    assert (rep.accepted, rep.rejected, rep.cursor_after) == (2, 1, 3)
    (failure,) = station.list_upstream_failures(DEST)
    assert (
        str(failure.observation_id) == bad_id
        and failure.server_seq == 2
        and "unknown metric" in failure.error
    )


def test_batch_422_is_isolated_to_the_bad_record(station):
    obs = _fill(station, 3)
    poison = str(obs[0].id)

    def behaviour(mutations):
        if any(m["observation"]["id"] == poison for m in mutations):
            raise UpstreamBatchInvalid("422")
        return _ok(mutations)

    rep = push_upstream(station, FakeTransport(behaviour), destination=DEST, client_id="a1")
    assert (rep.accepted, rep.rejected, rep.cursor_after) == (2, 1, 3)
    assert str(station.list_upstream_failures(DEST)[0].observation_id) == poison


def test_refused_stops_without_advancing(station):
    _fill(station, 2)

    def behaviour(mutations):
        raise UpstreamRefused("401")

    rep = push_upstream(station, FakeTransport(behaviour), destination=DEST, client_id="a1")
    assert rep.status == "refused" and station.upstream_cursor(DEST) == 0


def test_missing_results_is_a_protocol_error(station):
    _fill(station, 2)
    rep = push_upstream(station, FakeTransport(lambda m: _ok(m[:1])), destination=DEST, client_id="a1")
    assert rep.status == "protocol_error" and station.upstream_cursor(DEST) == 0


def test_payload_omits_none_fields_for_older_upstreams(station):
    _fill(station, 1)
    t = FakeTransport(_ok)
    push_upstream(station, t, destination=DEST, client_id="a1")
    obs = t.pushed[0][0]["observation"]
    assert "uncertainty" not in obs and "supersedes" not in obs and "device_id" not in obs
    assert obs["provenance"]["data_origin"] == "simulated"


def test_cursor_is_monotonic_and_per_destination(station):
    station.set_upstream_cursor("a", 5)
    with pytest.raises(ValueError):
        station.set_upstream_cursor("a", 4)
    assert station.upstream_cursor("b") == 0


def test_bad_batch_size():
    with pytest.raises(ValueError):
        push_upstream(
            InMemoryObservationRepository(), FakeTransport(_ok), destination=DEST, client_id="a", batch_size=0
        )


# --------------------------------------------------------------------------- real HTTP transport


@pytest.fixture
def http_server():
    state = {"status": 200, "body": {"results": []}, "seen": []}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers["Content-Length"])
            state["seen"].append(
                (self.path, self.headers.get("Authorization"), json.loads(self.rfile.read(length)))
            )
            payload = json.dumps(state["body"]).encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", state
    server.shutdown()


def test_http_transport_maps_status_codes(http_server):
    url, state = http_server
    t = HttpUpstreamTransport(url, timeout=5, bearer_token="tok")
    state["body"] = {"results": [{"observation_id": "x", "status": "accepted"}]}
    assert t.push("c", [{"mutation_id": "m"}])[0]["status"] == "accepted"
    path, auth, body = state["seen"][-1]
    assert path == "/api/v1/sync/push" and auth == "Bearer tok" and body["client_id"] == "c"
    for code, exc in ((422, UpstreamBatchInvalid), (401, UpstreamRefused), (503, UpstreamUnavailable)):
        state["status"] = code
        with pytest.raises(exc):
            t.push("c", [])


def test_http_transport_unreachable_is_unavailable():
    with pytest.raises(UpstreamUnavailable):
        HttpUpstreamTransport("http://127.0.0.1:9", timeout=1).push("c", [])


# ---------------------------------------------------------------------- from test_three_station.py

T = datetime(2026, 2, 1, 12, tzinfo=UTC)
SURGEON = HumanIssuer(principal_id="auth0|fs1", display_name="Flight Surgeon", role="flight_surgeon")


class Station:
    def __init__(self, repo=None):
        self.repo = repo or InMemoryObservationRepository()
        self.client = TestClient(create_app(Settings(repository="memory"), repository=self.repo))
        self.online = True

    # observation push transport
    def push(self, client_id, mutations):
        if not self.online:
            raise UpstreamUnavailable("link down")
        return self.client.post(
            "/api/v1/sync/push", json={"client_id": client_id, "mutations": mutations}
        ).json()["results"]

    # document push transport
    def push_documents(self, client_id, documents):
        if not self.online:
            raise UpstreamUnavailable("link down")
        r = self.client.post(
            "/api/v1/sync/documents/push", json={"client_id": client_id, "documents": documents}
        )
        if r.status_code >= 400:
            raise UpstreamRefused(str(r.status_code))
        return r.json()

    # document pull page fetcher
    def page(self, cursor):
        if not self.online:
            raise UpstreamUnavailable("link down")
        return self.client.get("/api/v1/sync/documents/pull", params={"cursor": cursor}).json()


def mission():
    return Mission(
        mission_id="SIM-M1",
        name="sim",
        launch_at=T - timedelta(days=10),
        crew=["SIM-T01"],
        data_origin=DataOrigin.SIMULATED,
        created_at=T - timedelta(days=20),
    )


def test_astronaut_to_spacecraft_to_ground(tmp_path):
    astronaut = SqliteObservationRepository(tmp_path / "astronaut.db")
    spacecraft, ground = Station(), Station()
    store_mission(astronaut, mission())
    for i in range(3):
        astronaut.add(make_obs("behavioral.sleep_duration", 7.0, day=i))
    assert push_upstream(astronaut, spacecraft, destination="spacecraft", client_id="astro-1").accepted == 3
    assert (
        push_documents_upstream(astronaut, spacecraft, destination="spacecraft", client_id="astro-1").accepted
        == 1
    )
    # spacecraft forwards to ground with its own cursors
    assert push_upstream(spacecraft.repo, ground, destination="ground", client_id="craft").accepted == 3
    assert (
        push_documents_upstream(spacecraft.repo, ground, destination="ground", client_id="craft").accepted
        == 1
    )
    assert (
        ground.repo.head_seq() == 3
        and ground.client.get("/api/v1/missions").json()[0]["mission_id"] == "SIM-M1"
    )
    # re-running is idempotent
    assert (
        push_documents_upstream(astronaut, spacecraft, destination="spacecraft", client_id="astro-1").sent
        == 0
    )
    astronaut.close()


def test_return_now_flows_ground_to_spacecraft_with_history_intact():
    ground, spacecraft = Station(), Station()
    store_mission(ground.repo, mission())
    cmd = ReturnNowCommand(
        command_id=uuid4(),
        mission_id="SIM-M1",
        issuer=SURGEON,
        issued_at=T,
        reason="Simulated drill.",
        mission_context="Simulated mission.",
    )
    issue_return_now(ground.repo, cmd)
    transition_command(
        ground.repo, cmd.command_id, CommandStatus.ACKNOWLEDGED, SURGEON, T + timedelta(minutes=1), "ack"
    )
    rep = pull_documents(spacecraft.repo, ground.page, source="ground", registry=build_registry())
    assert (rep.status, rep.accepted, rep.rejected) == ("complete", 4, 0)  # mission, command, 2 status events
    local, remote = command_state(spacecraft.repo, cmd.command_id), command_state(ground.repo, cmd.command_id)
    assert local == remote and [e.status.value for e in local.history] == ["issued", "acknowledged"]
    # pulling again changes nothing
    again = pull_documents(spacecraft.repo, ground.page, source="ground", registry=build_registry())
    assert again.sent == 0


def test_pull_survives_outage_and_resumes():
    ground, spacecraft = Station(), Station()
    store_mission(ground.repo, mission())
    ground.online = False
    down = pull_documents(spacecraft.repo, ground.page, source="ground")
    assert down.status == "unavailable" and spacecraft.repo.upstream_cursor("ground#documents-pull") == 0
    ground.online = True
    assert pull_documents(spacecraft.repo, ground.page, source="ground").accepted == 1


def test_orphan_status_event_is_rejected_and_audited():
    craft = Station()
    orphan = CommandStatusEvent(
        event_id=uuid4(), command_id=uuid4(), status=CommandStatus.ACKNOWLEDGED, actor=SURGEON, at=T
    )
    r = craft.client.post(
        "/api/v1/sync/documents/push",
        json={
            "client_id": "x",
            "documents": [{"kind": "command_event", "document": orphan.model_dump(mode="json")}],
        },
    ).json()
    assert r[0]["status"] == "rejected" and "not present yet" in r[0]["error"]


@pytest.mark.parametrize(
    "item,needle",
    [
        ({"kind": "observation", "document": {}}, "not replicable"),
        ({"kind": "mission", "document": {"mission_id": "x"}}, "invalid mission"),
        (
            {
                "kind": "command",
                "document": {
                    **ReturnNowCommand(
                        command_id=uuid4(),
                        mission_id="NOPE",
                        issuer=SURGEON,
                        issued_at=T,
                        reason="r",
                        mission_context="c",
                    ).model_dump(mode="json")
                },
            },
            "mission not present",
        ),
    ],
)
def test_replication_validates_like_local_writes(item, needle):
    r = (
        Station()
        .client.post("/api/v1/sync/documents/push", json={"client_id": "x", "documents": [item]})
        .json()
    )
    assert r[0]["status"] == "rejected" and needle in r[0]["error"]


def test_replicated_ai_explanation_still_honours_data_boundary():
    craft = Station()
    private = make_obs(provenance=measured_provenance())
    craft.repo.add(private)
    expl = AIExplanation(
        explanation_id=uuid4(),
        provider="gemini",
        model="t",
        created_at=T,
        requested_by="auth0|gc1",
        question="q",
        summary="s",
        evidence=["e"],
        cited_observation_ids=[private.id],
        input_data_classes=["simulated"],
    )
    r = craft.client.post(
        "/api/v1/sync/documents/push",
        json={
            "client_id": "x",
            "documents": [{"kind": "ai_explanation", "document": expl.model_dump(mode="json")}],
        },
    ).json()
    assert "D-022" in r[0]["error"]


def test_document_pull_paging():
    ground = Station()
    for i in range(3):
        store_mission(ground.repo, mission().model_copy(update={"mission_id": f"SIM-M{i}"}))
    page = ground.client.get("/api/v1/sync/documents/pull", params={"cursor": 0, "limit": 2}).json()
    assert len(page["changes"]) == 2 and page["has_more"] is True and page["next_cursor"] == 2
    rest = ground.client.get("/api/v1/sync/documents/pull", params={"cursor": page["next_cursor"]}).json()
    assert len(rest["changes"]) == 1 and rest["has_more"] is False
