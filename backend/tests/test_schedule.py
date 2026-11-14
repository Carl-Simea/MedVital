"""Measurement schedules (M2): model, mission-time resolution, coverage, storage, API."""

import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from conftest import make_obs, measured_provenance
from medvital.core.schedule import (
    Anchor,
    MeasurementSchedule,
    MissionPhase,
    MissionWindow,
    RecurringTimepoints,
    ScheduleBasis,
    SingleTimepoint,
    resolve_schedule,
    schedule_coverage,
)
from medvital.db.repository import AddStatus, InMemoryObservationRepository
from medvital.db.sqlite import SqliteObservationRepository

SLEEP = "behavioral.sleep_duration"
LAUNCH = datetime(2030, 3, 1, 12, 0, tzinfo=UTC)  # arbitrary test mission
RETURN = LAUNCH + timedelta(days=30)
MISSION = MissionWindow(launch_at=LAUNCH, return_at=RETURN)


def make_schedule(**kw) -> MeasurementSchedule:
    base = dict(
        id=uuid4(),
        subject_id="SIM-T01",
        metric=SLEEP,
        method="actigraphy",
        events=[SingleTimepoint(anchor=Anchor.LAUNCH, offset_days=-13)],
        basis=ScheduleBasis.SIMULATED,
        source="pytest",
        created_at=LAUNCH - timedelta(days=100),
    )
    base.update(kw)
    return MeasurementSchedule(**base)


# --------------------------------------------------------------------------- model


def test_protocol_basis_requires_source_ref():
    with pytest.raises(ValidationError):
        make_schedule(basis=ScheduleBasis.PROTOCOL)
    s = make_schedule(basis=ScheduleBasis.PROTOCOL, source_ref="doi:10.83263/whe7-1e26")
    assert s.source_ref.startswith("doi:")


@pytest.mark.parametrize(
    "kw",
    [
        {"metric": "nonsense.metric"},
        {"events": []},
        {"created_at": datetime(2030, 1, 1)},  # naive time
        {"extra_field": 1},
    ],
)
def test_invalid_schedules_rejected(kw):
    with pytest.raises(ValidationError):
        make_schedule(**kw)


def test_self_supersede_rejected():
    i = uuid4()
    with pytest.raises(ValidationError):
        make_schedule(id=i, supersedes=i)


def test_mission_window_order():
    with pytest.raises(ValidationError):
        MissionWindow(launch_at=LAUNCH, return_at=LAUNCH)


# --------------------------------------------------------------------------- resolution


def test_single_timepoints_hand_computed():
    s = make_schedule(
        events=[
            SingleTimepoint(anchor=Anchor.LAUNCH, offset_days=-13),  # 2030-02-16 12:00
            SingleTimepoint(anchor=Anchor.RETURN, offset_days=1, window_days=2),  # 2030-04-01 12:00
        ]
    )
    pre, post = resolve_schedule(s, MISSION)
    assert (pre.label, pre.planned_at, pre.phase) == ("L-13", LAUNCH - timedelta(days=13), MissionPhase.PREFLIGHT)
    assert pre.window_start == pre.planned_at and pre.window_end == pre.planned_at + timedelta(days=1)
    assert (post.label, post.planned_at, post.phase) == ("R+1", RETURN + timedelta(days=1), MissionPhase.POSTFLIGHT)
    assert post.window_start == post.planned_at - timedelta(days=2)
    assert post.window_end == post.planned_at + timedelta(days=3)
    assert pre.time_origin.value == "modeled"


def test_recurring_weekly_inflight_hand_computed():
    # L+0, L+7, L+14, L+21, L+28 (L+35 would pass R+0 = L+30) -> 5 events, all in flight
    s = make_schedule(
        events=[
            RecurringTimepoints(
                start_anchor=Anchor.LAUNCH, start_offset_days=0, end_anchor=Anchor.RETURN, end_offset_days=0, every_days=7
            )
        ]
    )
    events = resolve_schedule(s, MISSION)
    assert [e.label for e in events] == ["L+0", "L+7", "L+14", "L+21", "L+28"]
    assert {e.phase for e in events} == {MissionPhase.INFLIGHT}


def test_recurring_that_ends_before_start_is_an_error():
    s = make_schedule(
        events=[
            RecurringTimepoints(
                start_anchor=Anchor.RETURN, start_offset_days=0, end_anchor=Anchor.LAUNCH, end_offset_days=0, every_days=1
            )
        ]
    )
    with pytest.raises(ValueError):
        resolve_schedule(s, MISSION)


def test_return_day_is_postflight():
    s = make_schedule(events=[SingleTimepoint(anchor=Anchor.RETURN, offset_days=0)])
    assert resolve_schedule(s, MISSION)[0].phase is MissionPhase.POSTFLIGHT


# --------------------------------------------------------------------------- coverage


def _obs_at(t, **kw):
    o = make_obs(SLEEP, 7.0, **kw)
    return o.model_copy(update={"observed_at": t, "recorded_at": t})


def test_coverage_counts_per_origin_and_never_imputes():
    s = make_schedule(
        events=[
            SingleTimepoint(anchor=Anchor.LAUNCH, offset_days=-13),
            SingleTimepoint(anchor=Anchor.LAUNCH, offset_days=-1),
        ]
    )
    resolved = resolve_schedule(s, MISSION)
    first = resolved[0].planned_at
    observations = [
        _obs_at(first + timedelta(hours=3)),  # simulated, inside L-13 window
        _obs_at(first + timedelta(hours=5), provenance=measured_provenance()),  # measured, inside L-13
        _obs_at(first + timedelta(days=1)),  # exactly at window end (exclusive) -> unscheduled
        _obs_at(first, subject_id="SIM-T02"),  # other subject: ignored
    ]
    cov = schedule_coverage(s, resolved, observations)
    assert cov.planned_events == 2
    assert cov.events[0].observed_counts == {"measured": 1, "simulated": 1}
    assert cov.events[1].observed_counts == {}  # L-1 stays missing; nothing filled in
    assert cov.events_with_observations == {"measured": 1, "simulated": 1}
    assert cov.unscheduled_observations == {"simulated": 1}


def test_coverage_respects_schedule_context():
    s = make_schedule(context={"device": "W1"})
    resolved = resolve_schedule(s, MISSION)
    t = resolved[0].planned_at
    cov = schedule_coverage(s, resolved, [_obs_at(t, context={"device": "W2"}), _obs_at(t, context={"device": "W1"})])
    assert cov.events[0].observed_counts == {"simulated": 1}


# --------------------------------------------------------------------------- storage contract


@pytest.fixture(params=["memory", "sqlite"])
def repo(request, tmp_path):
    if request.param == "memory":
        yield InMemoryObservationRepository()
    else:
        r = SqliteObservationRepository(tmp_path / "gateway.db")
        yield r
        r.close()


def test_schedule_insert_duplicate_conflict(repo):
    s = make_schedule()
    assert repo.add_schedule(s).status is AddStatus.INSERTED
    assert repo.add_schedule(s).status is AddStatus.DUPLICATE
    changed = s.model_copy(update={"method": "diary"})
    out = repo.add_schedule(changed)
    assert out.status is AddStatus.CONFLICT
    assert repo.get_schedule(s.id).method == "actigraphy"  # original untouched
    assert repo.get_schedule(uuid4()) is None


def test_schedule_listing_and_current_only(repo):
    a = make_schedule()
    b = make_schedule(supersedes=a.id, method="actigraphy-v2")
    other = make_schedule(subject_id="SIM-T02")
    for s in (a, b, other):
        repo.add_schedule(s)
    assert [s.id for s in repo.list_schedules()] == [a.id, b.id, other.id]
    assert [s.id for s in repo.list_schedules(subject_id="SIM-T01")] == [a.id, b.id]
    assert [s.id for s in repo.list_schedules(subject_id="SIM-T01", current_only=True)] == [b.id]
    assert repo.list_schedules(metric="bone.areal_bmd") == []


def test_sqlite_schedules_survive_restart_and_are_append_only(tmp_path):
    path = tmp_path / "gateway.db"
    s = make_schedule()
    r1 = SqliteObservationRepository(path)
    r1.add_schedule(s)
    r1.close()
    r2 = SqliteObservationRepository(path)
    assert r2.get_schedule(s.id) == s
    r2.close()
    conn = sqlite3.connect(path)
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE measurement_schedules SET method = 'x'")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM measurement_schedules")
    conn.close()


# --------------------------------------------------------------------------- API


def _body(s: MeasurementSchedule) -> dict:
    return s.model_dump(mode="json")


def test_api_schedule_lifecycle(client):
    s = make_schedule(
        events=[
            SingleTimepoint(anchor=Anchor.LAUNCH, offset_days=-13),
            RecurringTimepoints(
                start_anchor=Anchor.LAUNCH, start_offset_days=0, end_anchor=Anchor.RETURN, end_offset_days=0, every_days=7
            ),
        ]
    )
    r = client.post("/api/v1/schedules", json=_body(s))
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    assert client.post("/api/v1/schedules", json=_body(s)).json()["status"] == "duplicate"
    assert client.get(f"/api/v1/schedules/{s.id}").json()["id"] == str(s.id)
    assert client.get(f"/api/v1/schedules/{uuid4()}").status_code == 404
    assert [x["id"] for x in client.get("/api/v1/schedules", params={"subject_id": "SIM-T01"}).json()] == [str(s.id)]

    window = {"launch_at": LAUNCH.isoformat(), "return_at": RETURN.isoformat()}
    resolved = client.get(f"/api/v1/schedules/{s.id}/resolve", params=window).json()
    assert [e["label"] for e in resolved] == ["L-13", "L+0", "L+7", "L+14", "L+21", "L+28"]
    assert {e["time_origin"] for e in resolved} == {"modeled"}

    obs = _obs_at(LAUNCH + timedelta(days=7, hours=2))
    assert client.post("/api/v1/observations", json={"observations": [obs.model_dump(mode="json")]}).status_code == 200
    cov = client.get(f"/api/v1/schedules/{s.id}/coverage", params=window).json()
    assert cov["planned_events"] == 6 and cov["events_with_observations"] == {"simulated": 1}

    bad_window = {"launch_at": RETURN.isoformat(), "return_at": LAUNCH.isoformat()}
    assert client.get(f"/api/v1/schedules/{s.id}/resolve", params=bad_window).status_code == 422


@pytest.mark.parametrize(
    "kw,needle",
    [
        ({"metric": "bone.not_a_metric"}, "unknown metric"),
        ({"context": {"site": "femoral_neck"}}, "context keys"),  # sleep accepts only `device`
        ({"supersedes": uuid4()}, "unknown schedule"),
    ],
)
def test_api_rejects_semantically_invalid_schedules(client, kw, needle):
    r = client.post("/api/v1/schedules", json=_body(make_schedule(**kw)))
    assert r.status_code == 200 and r.json()["status"] == "rejected" and needle in r.json()["error"]


def test_api_revision_must_keep_subject_and_metric(client):
    a = make_schedule()
    client.post("/api/v1/schedules", json=_body(a))
    moved = make_schedule(supersedes=a.id, subject_id="SIM-T02")
    assert "keep the subject" in client.post("/api/v1/schedules", json=_body(moved)).json()["error"]


def test_api_conflict_reported(client):
    a = make_schedule()
    client.post("/api/v1/schedules", json=_body(a))
    r = client.post("/api/v1/schedules", json=_body(a.model_copy(update={"method": "diary"}))).json()
    assert r["status"] == "rejected" and "immutable" in r["error"]
