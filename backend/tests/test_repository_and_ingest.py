from uuid import uuid4

import pytest

from medvital.core.observation import ModuleId
from medvital.core.provenance import DataOrigin
from medvital.db.repository import InMemoryObservationRepository
from medvital.ingest import ingest
from tests.conftest import make_obs


def test_add_many_distinguishes_new_duplicate_and_conflict():
    repo = InMemoryObservationRepository()
    obs = make_obs()
    assert repo.add_many([obs]).accepted == [obs.id]
    assert repo.add_many([obs]).duplicates == [obs.id]
    changed = make_obs(obs_id=obs.id, value=obs.value + 1)
    assert repo.add_many([changed]).conflicts == [obs.id]
    assert len(repo.query()) == 1


def test_query_filters_and_orders_by_time():
    repo = InMemoryObservationRepository()
    repo.add_many(
        [
            make_obs(day=2),
            make_obs(day=1),
            make_obs(module=ModuleId.BONE, metric="bmd_areal", unit="g/cm2", value=1.0),
            make_obs(astronaut_id="SIM-002"),
        ]
    )
    hr = repo.query(astronaut_id="SIM-001", module=ModuleId.CARDIOVASCULAR)
    assert [o.observed_at.day for o in hr] == [2, 3]
    assert len(repo.query(metric="bmd_areal")) == 1
    assert repo.query(origin=DataOrigin.MEASURED) == []
    assert len(repo.query(limit=2)) == 2


def test_changes_since_pages_through_all_rows_exactly_once():
    repo = InMemoryObservationRepository()
    items = [make_obs(day=d) for d in range(5)]
    repo.add_many(items)
    seen, cursor = [], 0
    while True:
        page = repo.changes_since(cursor, 2)
        seen.extend(page.observations)
        cursor = page.next_cursor
        if not page.has_more:
            break
    assert [o.id for o in seen] == [o.id for o in items]
    assert repo.changes_since(cursor, 2).observations == []


def test_changes_since_rejects_bad_arguments():
    repo = InMemoryObservationRepository()
    with pytest.raises(ValueError):
        repo.changes_since(-1, 10)
    with pytest.raises(ValueError):
        repo.changes_since(0, 0)


def test_ingest_accepts_valid_and_rejects_invalid_independently():
    repo = InMemoryObservationRepository()
    good = make_obs().model_dump(mode="json")
    bad_unit = make_obs(unit="kg").model_dump(mode="json")
    malformed = {"id": str(uuid4()), "astronaut_id": "SIM-001"}
    result = ingest(repo, [good, bad_unit, malformed, "not a dict"])  # type: ignore[list-item]
    assert result.accepted == [good["id"]]
    assert len(result.rejected) == 3
    reasons = " ".join(r.reason for r in result.rejected)
    assert "unit" in reasons
    assert len(repo.query()) == 1


def test_ingest_is_idempotent_and_reports_conflicts():
    repo = InMemoryObservationRepository()
    obs = make_obs()
    payload = obs.model_dump(mode="json")
    assert ingest(repo, [payload]).accepted == [payload["id"]]
    again = ingest(repo, [payload])
    assert again.accepted == [] and again.duplicates == [payload["id"]]
    altered = {**payload, "value": payload["value"] + 5}
    conflict = ingest(repo, [altered])
    assert [r.id for r in conflict.rejected] == [payload["id"]]
    assert "different content" in conflict.rejected[0].reason


def test_ingest_rejection_reason_does_not_echo_submitted_values():
    repo = InMemoryObservationRepository()
    payload = make_obs().model_dump(mode="json")
    payload["astronaut_id"] = "secret value!!"
    result = ingest(repo, [payload])
    assert "secret value" not in result.rejected[0].reason
