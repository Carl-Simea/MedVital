"""Live view of what the gateway is receiving, for the dashboard.

Read-only projection of the newest observation per (device, crew member, metric). Values
keep their data origin and quality; nothing is averaged across origins.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from medvital.core.schema import DataOrigin, ModuleId, Quality
from medvital.db.repository import ObservationRepository


class LiveReading(BaseModel):
    domain: ModuleId
    indicator: str
    metric: str
    value: float
    unit: str
    observed_at: datetime
    quality: Quality
    data_origin: DataOrigin
    source: str


class LiveDevice(BaseModel):
    device_id: str
    crew_id: str
    last_seen: datetime
    readings: list[LiveReading]


class LiveTotals(BaseModel):
    observations_stored: int
    rejected: int


class LiveResponse(BaseModel):
    server_time: datetime
    totals: LiveTotals
    devices: list[LiveDevice]
    notice: str = (
        "Live gateway view. Values labelled simulated are synthetic test signals, not astronaut data."
    )


def build_live(repo: ObservationRepository, now: datetime | None = None) -> LiveResponse:
    now = now or datetime.now(UTC)
    devices: dict[tuple[str, str], list[LiveReading]] = {}
    last_seen: dict[tuple[str, str], datetime] = {}
    for o in repo.latest_by_device_metric():
        if o.device_id is None:
            continue  # generated/legacy data has no device; not part of the live feed
        key = (o.device_id, o.subject_id)
        devices.setdefault(key, []).append(
            LiveReading(
                domain=o.module,
                indicator=o.metric.split(".", 1)[1],
                metric=o.metric,
                value=o.value,
                unit=o.unit,
                observed_at=o.observed_at,
                quality=o.quality,
                data_origin=o.provenance.data_origin,
                source=o.provenance.source,
            )
        )
        last_seen[key] = max(last_seen.get(key, o.observed_at), o.observed_at)
    live = [
        LiveDevice(
            device_id=d,
            crew_id=c,
            last_seen=last_seen[(d, c)],
            readings=sorted(devices[(d, c)], key=lambda r: (r.domain.value, r.indicator)),
        )
        for (d, c) in sorted(devices)
    ]
    return LiveResponse(
        server_time=now,
        totals=LiveTotals(observations_stored=repo.head_seq(), rejected=repo.rejection_count()),
        devices=live,
    )
