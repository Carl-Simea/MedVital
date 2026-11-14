"""Backend records: generic document store, missions, references, environmental events, artifacts,
RETURN_NOW commands, rule findings, AI explanations and the accepted-write audit."""

import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from conftest import make_obs, measured_provenance
from medvital.core.records import (
    AIExplanation,
    CommandStatus,
    DetectorContext,
    EnvironmentalEvent,
    EnvironmentalMeasurement,
    FindingCategory,
    HumanIssuer,
    Mission,
    ReturnNowCommand,
    RuleFinding,
    SourceArtifact,
)
from medvital.core.reference import PublishedReference, ReferencePopulation, Verification
from medvital.core.schema import DataOrigin, Provenance
from medvital.db.repository import AddStatus, InMemoryObservationRepository
from medvital.db.sqlite import SqliteObservationRepository
from medvital.ingest import ingest_observation
from medvital.records_service import (
    command_state,
    environmental_timeline,
    issue_return_now,
    list_commands,
    store_ai_explanation,
    store_artifact,
    store_environmental_event,
    store_finding,
    store_mission,
    store_reference,
    transition_command,
)
from medvital.registry import build_registry

T = datetime(2030, 3, 1, 12, tzinfo=UTC)
SURGEON = HumanIssuer(principal_id="auth0|surgeon1", display_name="Flight Surgeon", role="flight_surgeon")


@pytest.fixture(params=["memory", "sqlite"])
def repo(request, tmp_path):
    if request.param == "memory":
        yield InMemoryObservationRepository()
    else:
        r = SqliteObservationRepository(tmp_path / "station.db")
        yield r
        r.close()


def mission(**kw):
    base = dict(
        mission_id="SIM-MISSION-1",
        name="Simulated mission",
        launch_at=T,
        return_at=T + timedelta(days=180),
        crew=["SIM-T01", "SIM-T02"],
        data_origin=DataOrigin.SIMULATED,
        created_at=T - timedelta(days=30),
    )
    base.update(kw)
    return Mission(**base)


def donki_event(source_event_id="2030-03-02T00:00:00-SEP-001", **kw):
    base = dict(
        event_id=EnvironmentalEvent.make_id("NASA DONKI", source_event_id, None),
        source_system="NASA DONKI",
        event_type="SEP",
        source_event_id=source_event_id,
        start_time=T + timedelta(days=1),
        provenance=Provenance(
            data_origin=DataOrigin.MEASURED, source="NASA DONKI", source_ref="test://donki/sep"
        ),
    )
    base.update(kw)
    return EnvironmentalEvent(**base)


# --------------------------------------------------------------------------- generic store


def test_document_store_idempotent_conflict_and_time_order(repo):
    m1, m2 = mission(), mission(mission_id="SIM-MISSION-0", launch_at=T - timedelta(days=400), return_at=None)
    assert (
        repo.add_document("mission", m1.mission_id, m1, sort_time=m1.launch_at).status is AddStatus.INSERTED
    )
    assert (
        repo.add_document("mission", m1.mission_id, m1, sort_time=m1.launch_at).status is AddStatus.DUPLICATE
    )
    changed = m1.model_copy(update={"name": "renamed"})
    assert repo.add_document("mission", m1.mission_id, changed).status is AddStatus.CONFLICT
    repo.add_document("mission", m2.mission_id, m2, sort_time=m2.launch_at)
    assert [m.mission_id for m in repo.list_documents("mission", Mission, order_by_time=True)] == [
        "SIM-MISSION-0",
        "SIM-MISSION-1",
    ]
    assert repo.get_document("mission", "SIM-MISSION-1", Mission).name == "Simulated mission"
    assert repo.list_documents("mission", Mission, since=T) == [m1]


def test_documents_persist_and_are_append_only(tmp_path):
    path = tmp_path / "s.db"
    r = SqliteObservationRepository(path)
    store_mission(r, mission())
    ingest_observation(r, build_registry(), make_obs())  # gives write_audit a row (row triggers need rows)
    r.close()
    r2 = SqliteObservationRepository(path)
    assert r2.get_document("mission", "SIM-MISSION-1", Mission) is not None
    r2.close()
    conn = sqlite3.connect(path)
    for sql in ("UPDATE documents SET tag = 'x'", "DELETE FROM documents", "DELETE FROM write_audit"):
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute(sql)
    conn.close()


# --------------------------------------------------------------------------- missions


@pytest.mark.parametrize(
    "kw",
    [
        {"return_at": T - timedelta(days=1)},
        {"crew": []},
        {"crew": ["SIM-T01", "SIM-T01"]},
        {"launch_at": datetime(2030, 1, 1)},
    ],
)
def test_mission_validation(kw):
    with pytest.raises(ValidationError):
        mission(**kw)


# --------------------------------------------------------------------------- references


def reference(**kw):
    base = dict(
        reference_id="REF-TEST-0001",
        citation="Test Author. A test citation. Test Journal, 2030.",
        source_identifier="doi:10.0000/test",
        verification=Verification.UNVERIFIED,
        quantity="example areal BMD",
        metric="bone.areal_bmd",
        unit="g/cm2",
        statistic="mean",
        value=1.0,
        population=ReferencePopulation(description="test population", species="Homo sapiens", n=10),
        limitations="Test fixture only; not a real published value.",
        retrieved_at=T,
    )
    base.update(kw)
    return PublishedReference(**base)


def test_reference_rules(repo):
    reg = build_registry()
    assert store_reference(repo, reference(), reg).status == "accepted"
    assert store_reference(repo, reference(), reg).status == "duplicate"
    assert (
        "canonical unit"
        in store_reference(repo, reference(reference_id="REF-TEST-0002", unit="mg/cm3"), reg).error
    )
    assert (
        "unknown metric"
        in store_reference(repo, reference(reference_id="REF-TEST-0003", metric="bone.nope"), reg).error
    )
    assert (
        "unknown reference"
        in store_reference(repo, reference(reference_id="REF-TEST-0004", supersedes="REF-NOPE-1"), reg).error
    )
    assert repo.list_references(metric="bone.areal_bmd")[0].reference_id == "REF-TEST-0001"


@pytest.mark.parametrize(
    "kw",
    [
        {"reference_id": "TEST-1"},  # missing REF- prefix
        {"value": None},  # no value and no interval
        {"interval_lower": 1.0, "interval_upper": 0.5, "interval_kind": "range"},
        {"verification": Verification.VERIFIED_AT_SOURCE},  # without verifier/time
        {"limitations": ""},
        {"citation": ""},
    ],
)
def test_reference_validation(kw):
    with pytest.raises(ValidationError):
        reference(**kw)


def test_reference_is_not_an_observation(client):
    r = client.post("/api/v1/observations", json={"observations": [reference().model_dump(mode="json")]})
    assert r.status_code == 422


# --------------------------------------------------------------------------- environmental events


def test_environmental_event_rules(repo):
    assert store_environmental_event(repo, donki_event()).status == "accepted"
    bad_id = donki_event().model_copy(update={"event_id": uuid4()})
    assert "derived" in store_environmental_event(repo, bad_id).error
    orphan = donki_event("X-2", source_artifact_id=uuid4())
    assert "unknown artifact" in store_environmental_event(repo, orphan).error
    assert donki_event().applies_to_individual is False


def test_environmental_event_validation():
    sim = Provenance(data_origin=DataOrigin.SIMULATED, source="t", generator_version="t", seed=1)
    with pytest.raises(ValidationError):
        donki_event(provenance=sim)  # DONKI data can never be simulated
    with pytest.raises(ValidationError):
        donki_event(source_system="scenario")  # scenarios must be simulated
    with pytest.raises(ValidationError):
        donki_event(measurements=[EnvironmentalMeasurement(quantity="TOT_DOSE_B", value=1.0, unit="uGy/h")])
    with pytest.raises(ValidationError):
        donki_event(applies_to_individual=True)
    with pytest.raises(ValidationError):
        donki_event(subject_id="SIM-T01")  # no way to attach an event to a person


def test_environmental_timeline_replay_order(repo):
    later = donki_event("B", start_time=T + timedelta(days=3))
    earlier = donki_event("A", start_time=T + timedelta(days=2), event_type="CME")
    rad = EnvironmentalEvent(
        event_id=EnvironmentalEvent.make_id("MSL RAD", "P1#0", None),
        source_system="MSL RAD",
        event_type="dosimetry",
        source_event_id="P1#0",
        start_time=T,
        detector=DetectorContext(instrument="MSL RAD", detector="B", location="Mars surface (Gale crater)"),
        measurements=[EnvironmentalMeasurement(quantity="TOT_DOSE_B", value=10.0, unit="uGy/h")],
        provenance=Provenance(data_origin=DataOrigin.MEASURED, source="MSL RAD", source_ref="test://rad"),
    )
    for e in (later, earlier, rad):
        store_environmental_event(repo, e)
    assert [e.source_event_id for e in environmental_timeline(repo)] == ["P1#0", "A", "B"]
    assert [e.source_event_id for e in environmental_timeline(repo, event_type="CME")] == ["A"]
    assert [e.source_event_id for e in environmental_timeline(repo, since=T + timedelta(days=2.5))] == ["B"]


def test_artifact_id_is_derived(repo):
    sha = "a" * 64
    art = SourceArtifact(
        artifact_id=SourceArtifact.make_id("https://x/y.csv", sha),
        source_system="NASA OSDR",
        dataset_id="OSD-TEST",
        source_url="https://x/y.csv",
        original_filename="y.csv",
        sha256=sha,
        size_bytes=1,
        retrieved_at=T,
        import_method="test",
    )
    assert store_artifact(repo, art).status == "accepted"
    assert store_artifact(repo, art.model_copy(update={"artifact_id": uuid4()})).status == "rejected"


# --------------------------------------------------------------------------- RETURN_NOW


def command(**kw):
    base = dict(
        command_id=uuid4(),
        mission_id="SIM-MISSION-1",
        issuer=SURGEON,
        issued_at=T + timedelta(days=10),
        reason="Simulated drill: human decision recorded for demonstration.",
        mission_context="Simulated mission, flight day 10.",
    )
    base.update(kw)
    return ReturnNowCommand(**base)


def test_return_now_is_human_only_by_construction():
    for issuer in (
        {"principal_id": "gemini", "display_name": "AI", "role": "flight_surgeon", "issuer_type": "ai"},
        {"principal_id": "rules", "display_name": "engine", "role": "system"},
    ):
        with pytest.raises(ValidationError):
            command(issuer=issuer)
    with pytest.raises(ValidationError):
        command(reason="")


def test_return_now_lifecycle_and_audit(repo):
    store_mission(repo, mission())
    c = command(subject_ids=["SIM-T01"])
    assert issue_return_now(repo, c).status == "accepted"
    assert issue_return_now(repo, c).status == "duplicate"
    state = command_state(repo, c.command_id)
    assert state.status is CommandStatus.ISSUED and len(state.history) == 1
    t1 = c.issued_at + timedelta(minutes=5)
    assert (
        transition_command(repo, c.command_id, CommandStatus.ACKNOWLEDGED, SURGEON, t1, "ack").status
        == "accepted"
    )
    bad = transition_command(repo, c.command_id, CommandStatus.COMPLETED, SURGEON, t1, None)
    assert bad.status == "rejected" and "not allowed" in bad.error
    early = transition_command(repo, c.command_id, CommandStatus.IN_PROGRESS, SURGEON, c.issued_at, None)
    assert "precedes" in early.error
    transition_command(
        repo, c.command_id, CommandStatus.WITHDRAWN, SURGEON, t1 + timedelta(minutes=1), "drill over"
    )
    final = command_state(repo, c.command_id)
    assert [e.status.value for e in final.history] == ["issued", "acknowledged", "withdrawn"]
    assert (
        transition_command(
            repo, c.command_id, CommandStatus.ACKNOWLEDGED, SURGEON, t1 + timedelta(hours=1), None
        ).status
        == "rejected"
    )
    assert [x.command_id for x in list_commands(repo, "SIM-MISSION-1")] == [c.command_id]


def test_return_now_requires_known_mission_and_crew(repo):
    assert "unknown mission" in issue_return_now(repo, command()).error
    store_mission(repo, mission())
    assert "not in mission crew" in issue_return_now(repo, command(subject_ids=["SIM-T99"])).error


# --------------------------------------------------------------------------- findings and AI explanations


def finding():
    return RuleFinding(
        finding_id=RuleFinding.make_id("device_offline", "W1|2030"),
        rule_id="device_offline",
        rule_version="1",
        category=FindingCategory.DEVICE_OFFLINE,
        device_id="W1",
        evaluated_at=T,
        summary="No telemetry from W1 for longer than the configured window.",
    )


def test_finding_markers():
    f = finding()
    assert f.clinical is False and f.review_required is True
    with pytest.raises(ValidationError):
        RuleFinding(**{**f.model_dump(), "clinical": True})


def explanation(**kw):
    base = dict(
        explanation_id=uuid4(),
        provider="gemini",
        model="test-model",
        created_at=T,
        requested_by="auth0|ground1",
        question="Why is there a flag?",
        summary="A device stopped reporting.",
        evidence=["Finding device_offline for W1."],
        input_data_classes=["simulated"],
    )
    base.update(kw)
    return AIExplanation(**base)


def test_ai_explanation_must_cite_and_is_never_an_observation():
    with pytest.raises(ValidationError):
        explanation()  # cites nothing
    with pytest.raises(ValidationError):
        explanation(cited_report_ids=["r1"], is_observation=True)


def test_ai_explanation_data_boundary(repo):
    sim = make_obs()
    private = make_obs(provenance=measured_provenance())  # source_ref test://fixture/1: not public
    public = make_obs(
        provenance=Provenance(
            data_origin=DataOrigin.MEASURED, source="OSDR", source_ref="https://osdr.nasa.gov/x"
        )
    )
    for o in (sim, private, public):
        repo.add(o)
    store_finding(repo, finding())
    assert store_ai_explanation(repo, repo, explanation(cited_observation_ids=[sim.id])).status == "accepted"
    assert (
        store_ai_explanation(repo, repo, explanation(cited_observation_ids=[public.id])).status == "accepted"
    )
    assert "D-022" in store_ai_explanation(repo, repo, explanation(cited_observation_ids=[private.id])).error
    assert (
        "does not exist"
        in store_ai_explanation(repo, repo, explanation(cited_observation_ids=[uuid4()])).error
    )
    assert (
        store_ai_explanation(repo, repo, explanation(cited_finding_ids=[finding().finding_id])).status
        == "accepted"
    )
    assert (
        "does not exist" in store_ai_explanation(repo, repo, explanation(cited_finding_ids=[uuid4()])).error
    )


# --------------------------------------------------------------------------- accepted-write audit


def test_accepted_writes_are_audited_with_channel(repo):
    reg = build_registry()
    o = make_obs()
    ingest_observation(repo, reg, o, channel="sync", audit_context={"client_id": "station-A"})
    ingest_observation(repo, reg, o, channel="sync", audit_context={"client_id": "station-A"})  # duplicate
    ingest_observation(
        repo, reg, make_obs(unit="min", metric="behavioral.sleep_duration"), channel="api"
    )  # rejected
    (entry,) = repo.list_writes()
    assert (entry.observation_id, entry.channel, entry.client_id, entry.server_seq) == (
        o.id,
        "sync",
        "station-A",
        1,
    )


def test_telemetry_writes_are_audited(client):
    event = {
        "event_id": "EVT-1",
        "device_id": "W1",
        "crew_id": "SIM-T01",
        "timestamp": "2026-01-01T00:00:00Z",  # past: future times are skew-rejected
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
    assert client.post("/api/v1/telemetry", json={"events": [event]}).json()["accepted"] == 1
    repo = client.app.state.repository
    (entry,) = repo.list_writes()
    assert entry.channel == "telemetry" and entry.device_id == "W1"
