"""Deterministic, NON-CLINICAL rule engine (D-021).

Rules: device offline, invalid sensor data, missed scheduled measurement, synchronization failure,
space-weather notice (DONKI), statistical deviation for review. Outputs are ``RuleFinding`` review
flags. No rule applies a clinical threshold, labels risk, or touches RETURN_NOW commands: this
module has no import of the command functions and writes nothing but findings.

Every numeric parameter here is an *operational* engineering default (how long until a device counts
as silent, how far back to look). Each finding records the parameters that produced it.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

from medvital.analysis import AnalysisConfig, analyze
from medvital.core.module_spec import ModuleRegistry
from medvital.core.records import FindingCategory, RuleFinding
from medvital.core.schedule import MissionWindow, resolve_schedule, schedule_coverage
from medvital.core.schema import Quality
from medvital.db.repository import (
    DocumentRepository,
    ObservationRepository,
    ScheduleRepository,
    UpstreamStateRepository,
)
from medvital.records_service import environmental_timeline, list_missions

RULES_VERSION = "1"
_FAR_FUTURE_DAYS = 3650  # ongoing mission: return-anchored events cannot be missed yet
MAX_EVIDENCE = 50


class RuleConfig(BaseModel):
    """Operational parameters (engineering defaults, not clinical or scientific values)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    device_offline_after_s: float = Field(default=300.0, gt=0)
    invalid_data_window_s: float = Field(default=3600.0, gt=0)
    sync_failure_window_s: float = Field(default=86400.0, gt=0)
    space_weather_lookback_s: float = Field(default=86400.0, gt=0)
    deviation_window_s: float = Field(default=7 * 86400.0, gt=0)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)


class _Repo(ObservationRepository, DocumentRepository, ScheduleRepository, UpstreamStateRepository): ...


def _finding(
    rule: str, key: str, category: FindingCategory, now: datetime, summary: str, **kw
) -> RuleFinding:
    return RuleFinding(
        finding_id=RuleFinding.make_id(rule, key),
        rule_id=rule,
        rule_version=RULES_VERSION,
        category=category,
        evaluated_at=now,
        summary=summary[:2000],
        **kw,
    )


def device_offline(repo: _Repo, now: datetime, cfg: RuleConfig) -> list[RuleFinding]:
    latest: dict[str, tuple[datetime, str]] = {}
    for o in repo.latest_by_device_metric():
        if o.device_id is None:
            continue
        if o.device_id not in latest or o.observed_at > latest[o.device_id][0]:
            latest[o.device_id] = (o.observed_at, o.subject_id)
    out = []
    for device, (last, subject) in sorted(latest.items()):
        silent = (now - last).total_seconds()
        if silent > cfg.device_offline_after_s:
            out.append(
                _finding(
                    "device_offline",
                    f"{device}|{last.isoformat()}",
                    FindingCategory.DEVICE_OFFLINE,
                    now,
                    f"No observation from device {device} since {last.isoformat()} ({silent:.0f} s).",
                    device_id=device,
                    subject_id=subject,
                    window_start=last,
                    window_end=now,
                    parameters={"device_offline_after_s": str(cfg.device_offline_after_s)},
                )
            )
    return out


def invalid_sensor_data(repo: _Repo, now: datetime, cfg: RuleConfig) -> list[RuleFinding]:
    start = now - timedelta(seconds=cfg.invalid_data_window_s)
    by_device: dict[tuple[str, str], list[str]] = defaultdict(list)
    for o in repo.query(since=start, until=now + timedelta(microseconds=1), limit=100_000):
        if o.quality is not Quality.VALID:
            by_device[(o.device_id or "unknown", o.subject_id)].append(f"{o.id}:{o.quality.value}")
    return [
        _finding(
            "invalid_sensor_data",
            f"{device}|{subject}|{start.isoformat()}",
            FindingCategory.INVALID_SENSOR_DATA,
            now,
            f"{len(ids)} non-valid reading(s) from device {device} in the last "
            f"{cfg.invalid_data_window_s:.0f} s "
            "(stored and flagged, never dropped).",
            device_id=None if device == "unknown" else device,
            subject_id=subject,
            window_start=start,
            window_end=now,
            evidence_ids=ids[:MAX_EVIDENCE],
            parameters={"invalid_data_window_s": str(cfg.invalid_data_window_s)},
        )
        for (device, subject), ids in sorted(by_device.items())
    ]


def missed_scheduled_measurements(repo: _Repo, now: datetime, cfg: RuleConfig) -> list[RuleFinding]:
    out = []
    for mission in list_missions(repo):
        if mission.launch_at > now:
            continue
        window = MissionWindow(
            launch_at=mission.launch_at,
            return_at=mission.return_at or mission.launch_at + timedelta(days=_FAR_FUTURE_DAYS),
        )
        for subject in mission.crew:
            for schedule in repo.list_schedules(subject_id=subject, current_only=True):
                try:
                    resolved = resolve_schedule(schedule, window)
                except ValueError:
                    continue
                observations = repo.query(subject_id=subject, module=schedule.module, limit=100_000)
                coverage = schedule_coverage(schedule, resolved, observations)
                for ec in coverage.events:
                    if ec.event.window_end <= now and not ec.observed_counts:
                        out.append(
                            _finding(
                                "missed_scheduled_measurement",
                                f"{schedule.id}|{ec.event.label}|{ec.event.planned_at.isoformat()}",
                                FindingCategory.MISSED_SCHEDULED_MEASUREMENT,
                                now,
                                f"Planned {schedule.metric} ({schedule.method}) at {ec.event.label} has no "
                                "observation in its window. Nothing was imputed.",
                                mission_id=mission.mission_id,
                                subject_id=subject,
                                module=schedule.module,
                                window_start=ec.event.window_start,
                                window_end=ec.event.window_end,
                                evidence_ids=[str(schedule.id)],
                            )
                        )
    return out


def sync_failures(repo: _Repo, now: datetime, cfg: RuleConfig) -> list[RuleFinding]:
    start = now - timedelta(seconds=cfg.sync_failure_window_s)
    by_dest: dict[str, list[str]] = defaultdict(list)
    for f in repo.list_upstream_failures(limit=10_000):
        if start <= f.recorded_at <= now:
            by_dest[f.destination].append(f"{f.observation_id}:{f.error[:80]}")
    return [
        _finding(
            "sync_failure",
            f"{dest}|{start.isoformat()}",
            FindingCategory.SYNC_FAILURE,
            now,
            f"{len(ids)} observation(s) refused by upstream '{dest}' (kept locally and audited).",
            window_start=start,
            window_end=now,
            evidence_ids=ids[:MAX_EVIDENCE],
            parameters={"sync_failure_window_s": str(cfg.sync_failure_window_s), "destination": dest},
        )
        for dest, ids in sorted(by_dest.items())
    ]


def space_weather_notices(repo: _Repo, now: datetime, cfg: RuleConfig) -> list[RuleFinding]:
    start = now - timedelta(seconds=cfg.space_weather_lookback_s)
    return [
        _finding(
            "space_weather_notice",
            str(e.event_id),
            FindingCategory.SPACE_WEATHER_NOTICE,
            now,
            f"{e.source_system} {e.event_type} {e.source_event_id} at {e.start_time.isoformat()}. "
            "Environmental context only; not an individual's dose.",
            window_start=e.start_time,
            window_end=now,
            evidence_ids=[str(e.event_id)],
        )
        for e in environmental_timeline(repo, since=start, until=now + timedelta(microseconds=1))
        if e.source_system != "MSL RAD"  # detector series are context, not notices
    ]


def statistical_deviations(
    repo: _Repo, now: datetime, cfg: RuleConfig, registry: ModuleRegistry
) -> list[RuleFinding]:
    start = now - timedelta(seconds=cfg.deviation_window_s)
    observations = repo.query(until=now + timedelta(microseconds=1), limit=100_000)
    report = analyze(observations, cfg.analysis, registry)
    out = []
    for s in report.series:
        for a in s.anomalies:
            if a.observed_at < start:
                continue
            out.append(
                _finding(
                    "statistical_deviation_review",
                    a.observation_id,
                    FindingCategory.STATISTICAL_DEVIATION_REVIEW,
                    now,
                    f"{s.key.metric} = {a.value} {a.unit} [{a.data_origin.value}] at "
                    f"{a.observed_at.isoformat()}: |modified z| {abs(a.modified_z):.2f} > {a.cutoff} "
                    "relative to this subject's own baseline. "
                    "Statistical review flag, not a clinical finding.",
                    subject_id=s.key.subject_id,
                    device_id=s.key.device_id,
                    window_start=a.observed_at,
                    window_end=a.observed_at,
                    evidence_ids=[a.observation_id],
                    parameters={"modified_z_cutoff": str(a.cutoff), "method": a.method[:100]},
                )
            )
    return out


def evaluate(
    repo: _Repo, registry: ModuleRegistry, now: datetime, cfg: RuleConfig | None = None
) -> list[RuleFinding]:
    """Run every rule. Pure read: persisting findings is the caller's choice."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    cfg = cfg or RuleConfig()
    findings = [
        *device_offline(repo, now, cfg),
        *invalid_sensor_data(repo, now, cfg),
        *missed_scheduled_measurements(repo, now, cfg),
        *sync_failures(repo, now, cfg),
        *space_weather_notices(repo, now, cfg),
        *statistical_deviations(repo, now, cfg, registry),
    ]
    return sorted(findings, key=lambda f: (f.category.value, str(f.finding_id)))
