"""Non-clinical rule engine (D-021): each rule, determinism, and the RETURN_NOW boundary."""

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from conftest import make_obs
from medvital.analysis import AnalysisConfig, BaselineSpec
from medvital.core.records import (
    EnvironmentalEvent,
    FindingCategory,
    HumanIssuer,
    Mission,
    ReturnNowCommand,
)
from medvital.core.schedule import Anchor, MeasurementSchedule, ScheduleBasis, SingleTimepoint
from medvital.core.schema import DataOrigin, Provenance, Quality
from medvital.db.repository import InMemoryObservationRepository
from medvital.records_service import (
    command_state,
    issue_return_now,
    list_commands,
    store_environmental_event,
    store_finding,
    store_mission,
)
from medvital.registry import build_registry
from medvital.rules import RuleConfig, evaluate

NOW = datetime(2030, 6, 1, 12, tzinfo=UTC)
REG = build_registry()


def at(obs, t, **update):
    return obs.model_copy(update={"observed_at": t, "recorded_at": t, **update})


def cats(findings):
    return sorted(f.category.value for f in findings)


@pytest.fixture
def repo():
    return InMemoryObservationRepository()


def test_empty_station_has_no_findings(repo):
    assert evaluate(repo, REG, NOW) == []


def test_device_offline(repo):
    repo.add(
        at(
            make_obs("cardiovascular.heart_rate", 60, unit="{beats}/min"),
            NOW - timedelta(minutes=10),
            device_id="W1",
        )
    )
    repo.add(
        at(
            make_obs("cardiovascular.heart_rate", 61, unit="{beats}/min"),
            NOW - timedelta(seconds=30),
            device_id="W2",
        )
    )
    (f,) = [f for f in evaluate(repo, REG, NOW) if f.category is FindingCategory.DEVICE_OFFLINE]
    assert f.device_id == "W1" and f.parameters == {"device_offline_after_s": "300.0"}
    quiet = evaluate(repo, REG, NOW, RuleConfig(device_offline_after_s=3600))
    assert not [x for x in quiet if x.category is FindingCategory.DEVICE_OFFLINE]


def test_invalid_sensor_data_is_flagged_not_dropped(repo):
    bad = at(
        make_obs("cardiovascular.heart_rate", 0, unit="{beats}/min"),
        NOW - timedelta(minutes=1),
        device_id="W1",
        quality=Quality.INVALID,
    )
    repo.add(bad)
    (f,) = [f for f in evaluate(repo, REG, NOW) if f.category is FindingCategory.INVALID_SENSOR_DATA]
    assert f.evidence_ids == [f"{bad.id}:invalid"] and repo.get(bad.id) is not None


def _mission_with_schedule(repo, offset_days):
    store_mission(
        repo,
        Mission(
            mission_id="SIM-M1",
            name="sim",
            launch_at=NOW - timedelta(days=20),
            return_at=None,
            crew=["SIM-T01"],
            data_origin=DataOrigin.SIMULATED,
            created_at=NOW - timedelta(days=40),
        ),
    )
    sched = MeasurementSchedule(
        id=uuid4(),
        subject_id="SIM-T01",
        metric="behavioral.sleep_duration",
        method="actigraphy",
        events=[SingleTimepoint(anchor=Anchor.LAUNCH, offset_days=offset_days)],
        basis=ScheduleBasis.SIMULATED,
        source="pytest",
        created_at=NOW - timedelta(days=40),
    )
    repo.add_schedule(sched)
    return sched


def test_missed_scheduled_measurement(repo):
    _mission_with_schedule(repo, 5)  # L+5, window ended 14 days ago, no observation
    (f,) = [f for f in evaluate(repo, REG, NOW) if f.category is FindingCategory.MISSED_SCHEDULED_MEASUREMENT]
    assert f.mission_id == "SIM-M1" and "L+5" in f.summary and "Nothing was imputed" in f.summary


def test_scheduled_measurement_present_or_future_is_not_missed(repo):
    _mission_with_schedule(repo, 5)
    repo.add(at(make_obs("behavioral.sleep_duration", 7.0), NOW - timedelta(days=15) + timedelta(hours=1)))
    _mission_with_schedule(repo, 30)  # future window
    assert not [
        f for f in evaluate(repo, REG, NOW) if f.category is FindingCategory.MISSED_SCHEDULED_MEASUREMENT
    ]


def test_sync_failure(repo):
    repo.record_upstream_failure("spacecraft", uuid4(), 3, "unknown metric upstream")
    findings = evaluate(repo, REG, datetime.now(UTC))
    (f,) = [f for f in findings if f.category is FindingCategory.SYNC_FAILURE]
    assert f.parameters["destination"] == "spacecraft"


def test_space_weather_notice_is_environmental(repo):
    e = EnvironmentalEvent(
        event_id=EnvironmentalEvent.make_id("NASA DONKI", "TEST-SEP-9", None),
        source_system="NASA DONKI",
        event_type="SEP",
        source_event_id="TEST-SEP-9",
        start_time=NOW - timedelta(hours=2),
        provenance=Provenance(data_origin=DataOrigin.MEASURED, source="NASA DONKI", source_ref="test://sep"),
    )
    store_environmental_event(repo, e)
    (f,) = [f for f in evaluate(repo, REG, NOW) if f.category is FindingCategory.SPACE_WEATHER_NOTICE]
    assert f.subject_id is None and "not an individual's dose" in f.summary


def test_statistical_deviation_review_flag(repo):
    base = make_obs("behavioral.sleep_duration", 1.0)
    for i, v in enumerate([1, 2, 3, 4, 5, 9]):
        repo.add(at(base, NOW - timedelta(days=5 - i), id=uuid4(), value=float(v)))
    cfg = RuleConfig(analysis=AnalysisConfig(baseline=BaselineSpec(n=5)))
    (f,) = [
        f for f in evaluate(repo, REG, NOW, cfg) if f.category is FindingCategory.STATISTICAL_DEVIATION_REVIEW
    ]
    assert "not a clinical finding" in f.summary and f.clinical is False and f.review_required is True


def test_evaluation_is_deterministic_and_idempotent(repo):
    repo.add(
        at(
            make_obs("cardiovascular.heart_rate", 60, unit="{beats}/min"),
            NOW - timedelta(hours=1),
            device_id="W1",
        )
    )
    first, second = evaluate(repo, REG, NOW), evaluate(repo, REG, NOW)
    assert [f.finding_id for f in first] == [f.finding_id for f in second]
    assert store_finding(repo, first[0]).status == "accepted"
    assert store_finding(repo, second[0]).status == "duplicate"


def test_naive_now_rejected(repo):
    with pytest.raises(ValueError):
        evaluate(repo, REG, datetime(2030, 1, 1))


def test_rules_never_touch_return_now(repo):
    # Static: the rule engine imports no command function.
    src = Path(__file__).resolve().parents[1] / "medvital" / "rules.py"
    imported = {
        a.name for n in ast.walk(ast.parse(src.read_text())) if isinstance(n, ast.ImportFrom) for a in n.names
    }
    assert not imported & {"issue_return_now", "transition_command", "ReturnNowCommand", "CommandStatusEvent"}
    # Dynamic: an issued command is unchanged by evaluation, and evaluation creates none.
    store_mission(
        repo,
        Mission(
            mission_id="SIM-M1",
            name="sim",
            launch_at=NOW - timedelta(days=1),
            crew=["SIM-T01"],
            data_origin=DataOrigin.SIMULATED,
            created_at=NOW - timedelta(days=2),
        ),
    )
    cmd = ReturnNowCommand(
        command_id=uuid4(),
        mission_id="SIM-M1",
        issued_at=NOW - timedelta(hours=1),
        issuer=HumanIssuer(principal_id="auth0|s", display_name="S", role="flight_surgeon"),
        reason="drill",
        mission_context="sim",
    )
    issue_return_now(repo, cmd)
    before = command_state(repo, cmd.command_id)
    evaluate(repo, REG, NOW)
    assert command_state(repo, cmd.command_id) == before and len(list_commands(repo)) == 1
