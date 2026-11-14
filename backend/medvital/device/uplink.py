"""Device -> gateway uplink: HTTP transport, offline buffer, retry. Standard library only."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol


class UplinkError(Exception):
    """kind: 'network' (no response) or 'http' (server answered with an error status)."""

    def __init__(self, kind: str, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status = status


class Transport(Protocol):
    def post_events(self, events: list[dict[str, Any]]) -> dict[str, Any]: ...


class UrllibTransport:
    def __init__(self, gateway_url: str, timeout: float = 5.0) -> None:
        self.url = gateway_url.rstrip("/") + "/api/v1/telemetry"
        self.timeout = timeout

    def post_events(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        data = json.dumps({"events": events}).encode("utf-8")
        req = urllib.request.Request(self.url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 (operator-supplied URL)
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise UplinkError("http", f"HTTP {exc.code}", exc.code) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise UplinkError("network", str(getattr(exc, "reason", exc))) from exc


@dataclass
class FlushReport:
    sent: int = 0
    accepted: int = 0
    duplicate: int = 0
    rejected: int = 0
    error: str | None = None


@dataclass
class Uplink:
    """Buffers events and delivers them in batches.

    * Gateway unreachable / 5xx: events stay buffered in order and are retried.
    * Every delivered event gets a verdict (accepted / duplicate / rejected). Rejected events
      are final — the gateway has them in its audit log — and are counted here, not retried.
    * The buffer is in memory: it survives a gateway outage but not a device-process restart.
      If it overflows, the oldest events are discarded and ``dropped`` records how many.
    """

    transport: Transport
    batch_size: int = 100
    max_buffer: int = 100_000
    buffer: deque[dict[str, Any]] = field(default_factory=deque)
    dropped: int = 0
    total_accepted: int = 0
    total_duplicate: int = 0
    total_rejected: int = 0
    rejected_reasons: list[str] = field(default_factory=list)

    def enqueue(self, events: list[dict[str, Any]]) -> None:
        for event in events:
            if len(self.buffer) >= self.max_buffer:
                self.buffer.popleft()
                self.dropped += 1
            self.buffer.append(event)

    def flush(self) -> FlushReport:
        report = FlushReport()
        while self.buffer:
            batch = [self.buffer[i] for i in range(min(self.batch_size, len(self.buffer)))]
            try:
                response = self.transport.post_events(batch)
            except UplinkError as exc:
                if exc.kind == "http" and exc.status is not None and 400 <= exc.status < 500:
                    # The gateway refused the whole request; retrying the same bytes cannot succeed.
                    for _ in batch:
                        self.buffer.popleft()
                    self.total_rejected += len(batch)
                    report.rejected += len(batch)
                    self.rejected_reasons.append(f"batch refused: {exc}")
                    continue
                report.error = str(exc)
                return report
            for _ in batch:
                self.buffer.popleft()
            report.sent += len(batch)
            for result in response.get("results", []):
                status = result.get("status")
                if status == "accepted":
                    report.accepted += 1
                    self.total_accepted += 1
                elif status == "duplicate":
                    report.duplicate += 1
                    self.total_duplicate += 1
                else:
                    report.rejected += 1
                    self.total_rejected += 1
                    self.rejected_reasons.append(f"{result.get('event_id')}: {result.get('error')}")
        return report


def run_device(
    simulator: Any,
    uplink: Uplink,
    *,
    interval: float = 1.0,
    duration: float | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
    max_retry_delay: float = 10.0,
) -> None:
    """Tick the simulator, buffer its events, and flush to the gateway until ``duration`` elapses."""
    started = clock()
    retry_delay = 1.0
    next_attempt = started
    online: bool | None = None
    tick = 0
    while duration is None or (clock() - started).total_seconds() < duration:
        now = clock()
        uplink.enqueue(simulator.tick(now))
        if now >= next_attempt:
            report = uplink.flush()
            if report.error is None:
                retry_delay = 1.0
                next_attempt = now
                if online is not True:
                    log(f"[{simulator.device_id}] gateway reachable; buffer drained")
                online = True
            else:
                next_attempt = now + timedelta(seconds=retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)
                if online is not False:
                    log(f"[{simulator.device_id}] gateway UNREACHABLE ({report.error}); buffering")
                online = False
        tick += 1
        if tick % 10 == 0:
            log(
                f"[{simulator.device_id}] tick={tick} buffered={len(uplink.buffer)} "
                f"accepted={uplink.total_accepted} duplicate={uplink.total_duplicate} "
                f"rejected={uplink.total_rejected} dropped={uplink.dropped} synthetic=True"
            )
        sleep(interval)
