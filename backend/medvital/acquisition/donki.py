"""NASA DONKI -> EnvironmentalEvent parsers (only fields verified in docs/NASA_SOURCES.md §1).

* SEP: ``sepID, eventTime, instruments[{displayName}], link, linkedEvents[{activityID}], versionId``.
* CMEAnalysis: ``associatedCMEID, time21_5, catalog, isMostAccurate, link`` (numeric fields such as
  speed/halfAngle are NOT imported as measurements: their units were not verified).
* notifications: ``messageType, messageID, messageURL, messageIssueTime, messageBody``.

Timestamps are UTC strings with minute precision and a ``Z`` suffix (e.g. ``2024-05-10T12:59Z``).
DONKI records describe the space environment; they never become an astronaut's dose.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from medvital.core.records import EnvironmentalEvent, SourceArtifact
from medvital.core.schema import DataOrigin, Provenance

API_BASE = "https://api.nasa.gov/DONKI"
PARSER = "medvital.acquisition.donki v1"
SOURCE = "NASA DONKI"
SUPPORTED = ("SEP", "CMEAnalysis", "notifications")


def parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("missing timestamp")
    text = value.strip().replace("Z", "+00:00")
    t = datetime.fromisoformat(text)
    if t.tzinfo is None:
        raise ValueError(f"timestamp without timezone: {value!r}")
    return t.astimezone(UTC)


@dataclass
class ParseReport:
    events: list[EnvironmentalEvent] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # never silent: reason per skipped record


def _prov(artifact: SourceArtifact, link: str | None) -> Provenance:
    return Provenance(
        data_origin=DataOrigin.MEASURED,
        source=SOURCE,
        source_ref=(link or artifact.source_url)[:256],
        retrieved_at=artifact.retrieved_at,
        notes=(
            "DONKI event report (forecaster analysis of observations). Environmental context only; "
            "not an individual's dose."
        ),
    )


def _event(
    artifact: SourceArtifact, event_type: str, source_id: str, version: str | None, **kw
) -> EnvironmentalEvent:
    return EnvironmentalEvent(
        event_id=EnvironmentalEvent.make_id(SOURCE, source_id, version),
        source_system=SOURCE,
        event_type=event_type,
        source_event_id=source_id,
        source_version=version,
        source_artifact_id=artifact.artifact_id,
        provenance=_prov(artifact, kw.get("link")),
        **kw,
    )


def parse(endpoint: str, payload: bytes | str, artifact: SourceArtifact) -> ParseReport:
    if endpoint not in SUPPORTED:
        raise ValueError(f"unsupported DONKI endpoint {endpoint!r}; supported: {SUPPORTED}")
    data = json.loads(payload)
    if not isinstance(data, list):
        raise ValueError("DONKI response must be a JSON array")
    report = ParseReport()
    for i, rec in enumerate(data):
        try:
            report.events.append(_parse_one(endpoint, rec, artifact))
        except (ValueError, KeyError, TypeError) as exc:
            report.skipped.append(f"record {i}: {exc}")
    return report


def _ids(items: Iterable[Any] | None, key: str) -> list[str]:
    return [str(x[key])[:256] for x in items or [] if isinstance(x, dict) and x.get(key)]


def _parse_one(endpoint: str, rec: dict[str, Any], artifact: SourceArtifact) -> EnvironmentalEvent:
    if not isinstance(rec, dict):
        raise TypeError("record is not an object")
    if endpoint == "SEP":
        sep_id = rec["sepID"]
        instruments = ", ".join(_ids(rec.get("instruments"), "displayName")) or "not stated"
        return _event(
            artifact,
            "SEP",
            str(sep_id),
            str(rec["versionId"]) if rec.get("versionId") is not None else None,
            start_time=parse_time(rec["eventTime"]),
            summary=f"Solar energetic particle event. Instruments: {instruments}."[:2000],
            link=(rec.get("link") or None),
            linked_source_events=_ids(rec.get("linkedEvents"), "activityID"),
        )
    if endpoint == "CMEAnalysis":
        cme = rec["associatedCMEID"]
        t = parse_time(rec["time21_5"])
        catalog = str(rec.get("catalog") or "unknown")
        source_id = f"{cme}|{catalog}|{rec['time21_5']}"
        return _event(
            artifact,
            "CMEAnalysis",
            source_id,
            str(rec["versionId"]) if rec.get("versionId") is not None else None,
            start_time=t,
            summary=(
                f"CME analysis for {cme} (catalog {catalog}, most accurate: {rec.get('isMostAccurate')}). "
                "Numeric fields (speed, half angle, ...) not imported: units unverified."
            )[:2000],
            link=(rec.get("link") or None),
            linked_source_events=[str(cme)],
        )
    # notifications
    message_id = rec["messageID"]
    message_type = str(rec.get("messageType") or "unknown")
    return _event(
        artifact,
        f"notification:{message_type}",
        str(message_id),
        None,
        start_time=parse_time(rec["messageIssueTime"]),
        summary=str(rec.get("messageBody") or "")[:2000] or None,
        link=(rec.get("messageURL") or None),
    )


def endpoint_url(endpoint: str, start: str, end: str, api_key: str) -> str:
    """``start``/``end`` are ``YYYY-MM-DD``. The key is redacted from every stored URL."""
    if endpoint not in SUPPORTED:
        raise ValueError(f"unsupported DONKI endpoint {endpoint!r}")
    for d in (start, end):
        datetime.strptime(d, "%Y-%m-%d")
    return f"{API_BASE}/{endpoint}?startDate={start}&endDate={end}&api_key={api_key}"
