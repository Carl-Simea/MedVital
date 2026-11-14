"""Signal generator for one simulated wearable. Pure: no network, no sleeping, no clock reads."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np

GENERATOR_VERSION = "device-sim-0.1.0"
SOURCE = "simulated_sensor"


@dataclass(frozen=True)
class DeviceProfile:
    """Arbitrary signal centres for one simulated crew member (test values, not physiology)."""

    heart_rate_bpm: float
    dose_rate_ugy_h: float
    sleep_hours: float
    exercise_minutes: float


# Two arbitrary profiles so two devices produce visibly different traces.
DEFAULT_PROFILES: dict[str, DeviceProfile] = {
    "CREW-001": DeviceProfile(60.0, 10.0, 7.0, 30.0),
    "CREW-002": DeviceProfile(70.0, 12.0, 6.5, 45.0),
}
FALLBACK_PROFILE = DeviceProfile(65.0, 11.0, 7.0, 30.0)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class WearableSimulator:
    """Produces contract-shaped telemetry dicts (``medvital.core.telemetry.TelemetryEvent``).

    * every tick: heart rate (cardiovascular) and dose rate (radiation);
    * every ``slow_every`` ticks: a sleep-duration (behavioral) and a countermeasure-exercise
      (bone) log entry. A wearable does not measure bone density; the bone domain here carries
      activity logging only.
    """

    def __init__(
        self,
        device_id: str,
        crew_id: str,
        *,
        seed: int = 1,
        profile: DeviceProfile | None = None,
        start: datetime | None = None,
        slow_every: int = 30,
    ) -> None:
        self.device_id = device_id
        self.crew_id = crew_id
        self.seed = seed
        self.profile = profile or DEFAULT_PROFILES.get(crew_id, FALLBACK_PROFILE)
        self.slow_every = max(1, slow_every)
        self.radiation_factor = 1.0  # simulated scenario multiplier; 1.0 = baseline test signal
        self._rng = np.random.default_rng(seed)
        self._origin = start or datetime.now(UTC)
        # Unique per run, so restarting a device never reuses an event id with new content.
        self._session = self._origin.astimezone(UTC).strftime("%Y%m%dT%H%M%S")
        self._n = 0
        self._ticks = 0

    def _event(self, now: datetime, domain: str, indicator: str, value: float, unit: str) -> dict[str, Any]:
        self._n += 1
        return {
            "event_id": f"EVT-{self._session}-{self._n:06d}",
            "device_id": self.device_id,
            "crew_id": self.crew_id,
            "timestamp": _iso(now),
            "domain": domain,
            "indicator": indicator,
            "value": round(float(value), 2),
            "unit": unit,
            "source": SOURCE,
            "quality": "valid",
            "synthetic": True,
            "generator_version": GENERATOR_VERSION,
            "seed": self.seed,
        }

    def tick(self, now: datetime) -> list[dict[str, Any]]:
        p = self.profile
        t = (now - self._origin).total_seconds()
        rng = self._rng
        hr = max(1.0, p.heart_rate_bpm + 5.0 * math.sin(2 * math.pi * t / 120.0) + rng.normal(0, 1.5))
        dose = max(0.0, p.dose_rate_ugy_h * self.radiation_factor * (1 + rng.normal(0, 0.05)))
        events = [
            self._event(now, "cardiovascular", "heart_rate", hr, "bpm"),
            self._event(now, "radiation", "dose_rate", dose, "uGy/h"),
        ]
        if self._ticks % self.slow_every == 0:
            sleep = max(0.0, p.sleep_hours + rng.normal(0, 0.5))
            exercise = max(0.0, p.exercise_minutes + rng.normal(0, 5.0))
            events.append(self._event(now, "behavioral", "sleep_duration", sleep, "h"))
            events.append(self._event(now, "bone", "countermeasure_exercise_duration", exercise, "min"))
        self._ticks += 1
        return events
