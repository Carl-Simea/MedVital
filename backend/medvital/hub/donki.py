"""Space weather from NASA DONKI (CCMC, Goddard): live pull + a replay of a real past event.

Live: solar flares (FLR), CMEs and solar energetic particle events (SEP) from the last 30 days.
DONKI allows at most 60 days per query. Replay: the 17 Sep 2024 SEP event, so the demo does not
depend on the sun.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import UTC, date, datetime, timedelta
from typing import Any

BASES = [
    os.environ.get("MEDVITAL_DONKI_URL", "").rstrip("/"),
    "https://kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get",
    "https://api.nasa.gov/DONKI",  # needs ?api_key=DEMO_KEY
]
KINDS = ("SEP", "FLR", "CME")

# A real DONKI record (https://kauai.ccmc.gsfc.nasa.gov/DONKI/view/SEP/33467/2): >10 MeV protons at
# GOES-P crossed 10 pfu after the X4.5 flare from active region 13825 (peak 2024-09-14T15:29Z).
REPLAY_EVENT = {
    "sepID": "2024-09-17T07:35:00-SEP-001",
    "eventTime": "2024-09-17T07:35Z",
    "instruments": [{"displayName": "GOES-P: SEISS >10 MeV"}],
    "linkedEvents": [
        {"activityID": "2024-09-14T15:13:00-FLR-001"},
        {"activityID": "2024-09-14T15:36:00-CME-001"},
        {"activityID": "2024-09-16T22:49:00-IPS-001"},
    ],
    "link": "https://kauai.ccmc.gsfc.nasa.gov/DONKI/view/SEP/33467/2",
}


def describe(kind: str, rec: dict[str, Any]) -> tuple[str, str, str, str | None]:
    """(id, event time, one-line summary, link) for a DONKI record."""
    if kind == "SEP":
        inst = (
            ", ".join(i.get("displayName", "") for i in rec.get("instruments") or [])
            or "instrument not stated"
        )
        linked = [e.get("activityID", "") for e in rec.get("linkedEvents") or []]
        flare = next((x for x in linked if "FLR" in x), None)
        extra = f", linked to flare {flare}" if flare else ""
        return (
            rec["sepID"],
            rec["eventTime"],
            f"Solar energetic particle event ({inst}{extra}).",
            rec.get("link"),
        )
    if kind == "FLR":
        cls = rec.get("classType") or "?"
        return (
            rec["flrID"],
            rec.get("peakTime") or rec["beginTime"],
            f"Class {cls} solar flare.",
            rec.get("link"),
        )
    cme = rec.get("activityID")
    return cme, rec["startTime"], "Coronal mass ejection.", rec.get("link")


def fetch(kind: str, days: int = 30, timeout: float = 8.0) -> tuple[list[dict[str, Any]], str]:
    """Returns (records, base url used). Raises the last error if every base fails."""
    end = date.today()
    start = end - timedelta(days=days)
    last: Exception | None = None
    for base in [b for b in BASES if b]:
        url = f"{base}/{kind}?startDate={start}&endDate={end}"
        if "api.nasa.gov" in base:
            url += "&api_key=" + os.environ.get("NASA_API_KEY", "DEMO_KEY")
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (fixed hosts)
                body = resp.read().decode() or "[]"
            data = json.loads(body)
            return (data if isinstance(data, list) else []), base
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(str(last))


def now() -> datetime:
    return datetime.now(UTC)
