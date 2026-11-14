"""Repository contract tests. Parametrise ``repo`` with every implementation."""

from datetime import timedelta
from uuid import uuid4

import pytest

from conftest import T0, make_obs, measured_provenance
from medvital.core.schema import DataOrigin, ModuleId
from medvital.db.repository import AddStatus, InMemoryObservationRepository
from medvital.db.sqlite import SqliteObservationRepository


@pytest.fixture(params=["memory", "sqlite"])
def repo(request, tmp_path):
    if request.param == "memory":
        yield InMemoryObservationRepository()
    else:
        r = SqliteObservationRepository(tmp_path / "gateway.db")
        yield r
        r.close()


def test_insert_then_duplicate(repo):
    o = make_obs()
    first = repo.add(o)
    again = repo.add(o)
    assert first.status is AddStatus.INSERTED and first.server_seq == 1
    assert again.status is AddStatus.DUPLICATE and again.server_seq == 1
    assert repo.head_seq() == 1


def test_same_id_different_content_conflicts_and_stores_nothing(repo):
    i = uuid4()
    repo.add(make_obs(value=1.0, id=i))
    out = repo.add(make_obs(value=2.0, id=i))
    assert out.status is AddStatus.CONFLICT
    assert repo.get(i).observation.value == 1.0
    assert repo.head_seq() == 1


def test_server_seq_strictly_increasing(repo):
    seqs = [repo.add(make_obs(day=i)).server_seq for i in range(5)]
    assert seqs == [1, 2, 3, 4, 5]


def test_changes_since_cursor(repo):
    for i in range(5):
        repo.add(make_obs(day=i))
    assert [r.server_seq for r in repo.changes_since(2, limit=10)] == [3, 4, 5]
    assert [r.server_seq for r in repo.changes_since(0, limit=2)] == [1, 2]
    assert repo.changes_since(5) == []


def test_changes_since_subject_filter(repo):
    repo.add(make_obs(subject_id="SIM-A"))
    repo.add(make_obs(subject_id="SIM-B"))
    assert [r.observation.subject_id for r in repo.changes_since(0, subject_id="SIM-B")] == ["SIM-B"]


def test_query_filters(repo):
    repo.add(make_obs(subject_id="SIM-A", day=0))
    repo.add(make_obs("bone.areal_bmd", 1.0, subject_id="SIM-A", day=1))
    repo.add(make_obs(subject_id="SIM-A", day=2, provenance=measured_provenance()))
    assert len(repo.query(subject_id="SIM-A")) == 3
    assert len(repo.query(module=ModuleId.BONE)) == 1
    assert len(repo.query(data_origin=DataOrigin.MEASURED)) == 1
    assert len(repo.query(since=T0 + timedelta(days=1))) == 2
    assert len(repo.query(until=T0 + timedelta(days=1))) == 1
    assert len(repo.query(limit=2)) == 2


def test_query_is_time_ordered(repo):
    for d in (3, 1, 2):
        repo.add(make_obs(day=d))
    days = [(o.observed_at - T0).days for o in repo.query()]
    assert days == [1, 2, 3]
