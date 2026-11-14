"""Three-station data contracts with real FastAPI apps: astronaut -> spacecraft -> ground (push) and
ground -> spacecraft (pull of RETURN_NOW and other records). All payloads are simulated test data."""

from datetime import UTC, datetime, timedelta
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
    UpstreamRefused,
    UpstreamUnavailable,
    pull_documents,
    push_documents_upstream,
    push_upstream,
)

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
