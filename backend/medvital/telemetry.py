"""Spacecraft-gateway telemetry ingestion: wire event -> HealthObservation -> local store.

Every event gets exactly one outcome — accepted, duplicate, or rejected — and every
rejection is written to the rejection audit log with its reason and raw payload. Nothing
is silently discarded (briefing §8).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid5

from pydantic import ValidationError

from medvital.core.module_spec import ModuleRegistry, ObservationRejected
from medvital.core.schema import DataOrigin, HealthObservation, Provenance
from medvital.core.telemetry import (
    TelemetryEvent,
    TelemetryResponse,
    TelemetryResult,
    TelemetryStatus,
)
from medvital.db.repository import AddStatus, ObservationRepository

_NAMESPACE = UUID("2c0f6f4e-9d0b-4f4e-8f5e-6a1f5d4b7c10")
SOURCE = "telemetry"


def observation_id(device_id: str, event_id: str) -> UUID:
    """Deterministic: the same (device, event) always maps to the same observation id."""
    return uuid5(_NAMESPACE, f"{device_id}|{event_id}")


def event_to_observation(event: TelemetryEvent, registry: ModuleRegistry) -> HealthObservation:
    definition = registry.resolve_indicator(event.domain, event.indicator)
    if not definition.accepts_unit(event.unit):
        raise ObservationRejected(
            f"unit {event.unit!r} not accepted for {definition.metric}; expected "
            f"{definition.unit!r} (aliases: {', '.join(definition.unit_aliases) or 'none'})"
        )
    if event.synthetic:
        provenance = Provenance(
            data_origin=DataOrigin.SIMULATED,
            source=event.source,
            source_ref=event.source_ref,
            generator_version=event.generator_version,
            seed=event.seed,
        )
    else:
        provenance = Provenance(
            data_origin=DataOrigin.MEASURED,
            source=event.source,
            source_ref=event.source_ref,
            generator_version=event.generator_version,
            seed=event.seed,
        )
    return HealthObservation(
        id=observation_id(event.device_id, event.event_id),
        subject_id=event.crew_id,
        module=event.domain,
        metric=definition.metric,
        value=event.value,
        unit=definition.unit,
        observed_at=event.timestamp,
        recorded_at=event.timestamp,
        device_id=event.device_id,
        quality=event.quality,
        uncertainty=event.uncertainty,
        provenance=provenance,
    )


def _describe(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc'])) or 'event'}: {e['msg']}" for e in exc.errors())


def ingest_telemetry(
    repo: ObservationRepository,
    registry: ModuleRegistry,
    raw_events: list[Any],
    *,
    max_future_skew_seconds: int = 300,
    now: datetime | None = None,
    authorize: Callable[[HealthObservation], str | None] | None = None,
) -> TelemetryResponse:
    now = now or datetime.now(UTC)
    latest_allowed = now + timedelta(seconds=max_future_skew_seconds)
    results: list[TelemetryResult] = []

    def reject(raw: Any, event_id: str | None, reason: str) -> None:
        payload = raw if isinstance(raw, dict) else {"raw": repr(raw)}
        device = payload.get("device_id") if isinstance(payload.get("device_id"), str) else None
        repo.record_rejection(source=SOURCE, device_id=device, reason=reason, payload=payload)
        results.append(TelemetryResult(event_id=event_id, status=TelemetryStatus.REJECTED, error=reason))

    for raw in raw_events:
        raw_id = None
        if isinstance(raw, dict) and isinstance(raw.get("event_id"), str):
            raw_id = raw["event_id"]
        try:
            event = TelemetryEvent.model_validate(raw)
        except ValidationError as exc:
            reject(raw, raw_id, _describe(exc))
            continue
        if event.timestamp > latest_allowed:
            reject(
                raw,
                event.event_id,
                f"timestamp is more than {max_future_skew_seconds}s in the future (clock skew?)",
            )
            continue
        try:
            observation = event_to_observation(event, registry)
            problem = authorize(observation) if authorize is not None else None
            if problem:
                reject(raw, event.event_id, f"authorization: {problem}")
                continue
            registry.validate(observation)
        except ObservationRejected as exc:
            reject(raw, event.event_id, str(exc))
            continue
        except ValidationError as exc:
            reject(raw, event.event_id, _describe(exc))
            continue
        outcome = repo.add(observation)
        if outcome.status is AddStatus.CONFLICT:
            reject(raw, event.event_id, "event_id already used by this device with different content")
        else:
            inserted = outcome.status is AddStatus.INSERTED
            if inserted:
                repo.record_write(
                    server_seq=outcome.server_seq,
                    observation_id=observation.id,
                    channel=SOURCE,
                    client_id=None,
                    device_id=observation.device_id,
                )
            status = TelemetryStatus.ACCEPTED if inserted else TelemetryStatus.DUPLICATE
            results.append(
                TelemetryResult(event_id=event.event_id, status=status, server_seq=outcome.server_seq)
            )

    counts = {s: sum(1 for r in results if r.status is s) for s in TelemetryStatus}
    return TelemetryResponse(
        results=results,
        accepted=counts[TelemetryStatus.ACCEPTED],
        duplicate=counts[TelemetryStatus.DUPLICATE],
        rejected=counts[TelemetryStatus.REJECTED],
    )
