"""Acquisition and ingestion (no network: fake fetcher). Fixtures are SYNTHETIC test records shaped like
the verified DONKI fields (docs/NASA_SOURCES.md §1); they are not NASA data."""

import json
from datetime import UTC, datetime

import pytest

from medvital.acquisition import donki
from medvital.acquisition.download import download, http_fetch, redact_url, verify
from medvital.acquisition.ingest import ingest_donki, rad_url, register_artifact
from medvital.db.repository import InMemoryObservationRepository
from medvital.records_service import environmental_timeline, list_artifacts

NOW = datetime(2030, 5, 1, tzinfo=UTC)

SEP = [
    {
        "sepID": "TEST-SEP-001",
        "eventTime": "2030-04-10T12:59Z",
        "instruments": [{"displayName": "TEST-INSTR"}],
        "link": "test://sep/1",
        "linkedEvents": [{"activityID": "TEST-FLR-001"}],
        "versionId": 1,
    },
    {"sepID": "TEST-SEP-002", "eventTime": "not-a-time"},  # malformed: must be reported, not dropped silently
]
CME = [
    {
        "associatedCMEID": "TEST-CME-001",
        "time21_5": "2030-04-11T01:00Z",
        "catalog": "TEST",
        "isMostAccurate": True,
        "speed": 999,
        "halfAngle": 45,
        "link": "test://cme/1",
    }
]
NOTE = [
    {
        "messageType": "FLR",
        "messageID": "TEST-MSG-001",
        "messageURL": "test://msg/1",
        "messageIssueTime": "2030-04-10T13:00Z",
        "messageBody": "Synthetic test notification.",
    }
]


def fetcher(body):
    def fetch(url):
        fetch.urls.append(url)
        return (body if isinstance(body, bytes) else json.dumps(body).encode()), "application/json"

    fetch.urls = []
    return fetch


def get(tmp_path, body, endpoint="SEP"):
    url = donki.endpoint_url(endpoint, "2030-04-01", "2030-04-30", "SECRET-KEY-123")
    return download(
        url,
        tmp_path,
        source_system="NASA DONKI",
        dataset_id=f"DONKI/{endpoint}",
        original_filename=f"{endpoint}.json",
        fetch=fetcher(body),
        now=lambda: NOW,
    )


def test_download_stores_unmodified_file_and_redacts_key(tmp_path):
    got = get(tmp_path, SEP)
    assert got.path.read_bytes() == json.dumps(SEP).encode()
    assert got.path.parent.name == got.artifact.sha256
    assert "SECRET-KEY-123" not in got.artifact.model_dump_json() and "api_key" not in got.artifact.source_url
    assert [s.step for s in got.artifact.processing_history] == ["download", "checksum"]
    assert verify(got.path, got.artifact)


def test_tampered_file_is_detected_and_never_overwritten(tmp_path):
    got = get(tmp_path, SEP)
    got.path.write_bytes(b"tampered")
    assert not verify(got.path, got.artifact)
    with pytest.raises(RuntimeError, match="does not match"):
        get(tmp_path, SEP)
    with pytest.raises(ValueError, match="checksum"):
        ingest_donki(InMemoryObservationRepository(), "SEP", got.path, got.artifact)


def test_redact_url_keeps_other_params():
    assert redact_url("https://x/y?a=1&api_key=S&b=2") == "https://x/y?a=1&b=2"


def test_only_https_is_fetched():
    with pytest.raises(ValueError):
        http_fetch("http://example.com/x")


def test_ingest_sep_reports_skips_and_is_idempotent(tmp_path):
    repo = InMemoryObservationRepository()
    got = get(tmp_path, SEP)
    first = ingest_donki(repo, "SEP", got.path, got.artifact, now=lambda: NOW)
    assert (first.artifact_status, first.accepted, len(first.skipped)) == ("accepted", 1, 1)
    assert "record 1" in first.skipped[0]
    again = ingest_donki(repo, "SEP", got.path, got.artifact, now=lambda: NOW)
    assert (again.artifact_status, again.accepted, again.duplicate) == ("duplicate", 0, 1)
    (event,) = environmental_timeline(repo)
    assert event.source_event_id == "TEST-SEP-001" and event.linked_source_events == ["TEST-FLR-001"]
    assert event.source_artifact_id == got.artifact.artifact_id and event.applies_to_individual is False
    assert event.provenance.data_origin.value == "measured" and event.start_time == datetime(
        2030, 4, 10, 12, 59, tzinfo=UTC
    )
    (art,) = list_artifacts(repo)
    assert [s.step for s in art.processing_history][-1] == "parse:donki_SEP"


def test_cme_numeric_fields_not_imported(tmp_path):
    repo = InMemoryObservationRepository()
    got = get(tmp_path, CME, "CMEAnalysis")
    ingest_donki(repo, "CMEAnalysis", got.path, got.artifact, now=lambda: NOW)
    (e,) = environmental_timeline(repo)
    assert e.measurements == [] and "units unverified" in e.summary and "999" not in e.summary


def test_notifications(tmp_path):
    repo = InMemoryObservationRepository()
    got = get(tmp_path, NOTE, "notifications")
    ingest_donki(repo, "notifications", got.path, got.artifact, now=lambda: NOW)
    (e,) = environmental_timeline(repo)
    assert e.event_type == "notification:FLR" and e.summary == "Synthetic test notification."


def test_bad_inputs_rejected(tmp_path):
    with pytest.raises(ValueError):
        donki.endpoint_url("FLR", "2030-01-01", "2030-01-02", "k")  # endpoint fields unverified
    with pytest.raises(ValueError):
        donki.endpoint_url("SEP", "01/01/2030", "2030-01-02", "k")
    with pytest.raises(ValueError):
        donki.parse("SEP", b'{"not": "a list"}', get(tmp_path, SEP).artifact)
    for bad in ("../secret", "https://evil/x"):
        with pytest.raises(ValueError):
            rad_url(bad)


def test_register_artifact_without_parsing(tmp_path):
    repo = InMemoryObservationRepository()
    got = download(
        "https://example.org/a.csv",
        tmp_path,
        source_system="NASA OSDR",
        dataset_id="OSD-TEST",
        original_filename="a.csv",
        fetch=fetcher(b"a,b\n1,2\n"),
        now=lambda: NOW,
    )
    assert register_artifact(repo, got.artifact).artifact_status == "accepted"
    assert register_artifact(repo, got.artifact).artifact_status == "duplicate"
