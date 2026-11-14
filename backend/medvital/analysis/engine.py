"""Analysis engine: validated observations -> ``AnalysisReport``.

Responsibilities here are adaptation and bookkeeping only (grouping, exclusions,
provenance). All arithmetic lives in ``analysis.calculations``.

Series rule: values are compared only within one (subject, metric, unit, data_origin,
device_id, full context) series. Simulated, measured and modeled values are never pooled,
and neither are different devices, sites, instruments or sessions.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Sequence

import numpy as np
import pandas as pd

from medvital.analysis import calculations as calc
from medvital.analysis.models import (
    UNSPECIFIED_QUALITY,
    AnalysisConfig,
    AnalysisReport,
    AnomalyFlag,
    BaselineSummary,
    DataQualityReport,
    DescriptiveStats,
    Deviation,
    ExcludedObservation,
    ExclusionReason,
    GapInfo,
    MissingSeries,
    ProvenanceDigest,
    SeriesAnalysis,
    SeriesKey,
)
from medvital.core.module_spec import ModuleRegistry, ObservationRejected
from medvital.core.schema import DataOrigin, HealthObservation

ANOMALY_METHOD = "modified z-score vs own baseline (0.6745*(x-median)/MAD), Iglewicz & Hoaglin 1993"
_KEY_COLUMNS = ["subject_id", "metric", "unit", "data_origin", "device_id", "context"]


def _quality_of(o: HealthObservation) -> str:
    # ``quality`` / ``device_id`` are not in schema v1 of this checkout; read them when present
    # so the engine works unchanged once the telemetry fields land (see docs/DECISIONS.md D-018).
    q = getattr(o, "quality", None)
    return UNSPECIFIED_QUALITY if q is None else str(getattr(q, "value", q))


def _device_of(o: HealthObservation) -> str:
    d = getattr(o, "device_id", None)
    return "" if d is None else str(d)


def _finite_or_none(x: float) -> float | None:
    return float(x) if np.isfinite(x) else None


def _stats_model(s: calc.Descriptive) -> DescriptiveStats:
    return DescriptiveStats(**s.__dict__)


def analyze(
    observations: Iterable[HealthObservation],
    config: AnalysisConfig | None = None,
    registry: ModuleRegistry | None = None,
) -> AnalysisReport:
    """Analyse observations. Pass ``registry`` to re-run semantic validation; failures are
    reported as excluded (``rejected``), never silently dropped."""
    cfg = config or AnalysisConfig()
    obs = list(observations)
    excluded: list[ExcludedObservation] = []

    accepted: list[HealthObservation] = []
    for o in obs:
        if registry is not None:
            try:
                registry.validate(o)
            except ObservationRejected as exc:
                excluded.append(
                    ExcludedObservation(
                        observation_id=str(o.id), reason=ExclusionReason.REJECTED, detail=str(exc)
                    )
                )
                continue
        accepted.append(o)

    superseded = {o.supersedes for o in accepted if o.supersedes is not None}
    by_id = {str(o.id): o for o in accepted}
    rows = []
    for o in accepted:
        quality = _quality_of(o)
        if o.id in superseded:
            exclusion = ExclusionReason.SUPERSEDED.value
            excluded.append(
                ExcludedObservation(
                    observation_id=str(o.id),
                    reason=ExclusionReason.SUPERSEDED,
                    detail="superseded by a later observation in the input",
                )
            )
        elif quality not in cfg.analyzed_qualities:
            exclusion = ExclusionReason.QUALITY.value
            excluded.append(
                ExcludedObservation(
                    observation_id=str(o.id), reason=ExclusionReason.QUALITY, detail=f"quality={quality}"
                )
            )
        else:
            exclusion = ""
        rows.append(
            {
                "id": str(o.id),
                "subject_id": o.subject_id,
                "metric": o.metric,
                "unit": o.unit,
                "data_origin": o.provenance.data_origin.value,
                "device_id": _device_of(o),
                "context": json.dumps(o.context, sort_keys=True, separators=(",", ":")),
                "t": o.observed_at.timestamp(),
                "value": o.value,
                "quality": quality,
                "exclusion": exclusion,
            }
        )

    series: list[SeriesAnalysis] = []
    if rows:
        df = pd.DataFrame(rows)
        for key_values, part in df.groupby(_KEY_COLUMNS, sort=True):
            part = part.sort_values(["t", "id"], kind="stable").reset_index(drop=True)
            series.append(_analyze_series(dict(zip(_KEY_COLUMNS, key_values, strict=True)), part, by_id, cfg))

    analyzed_pairs = {(s.key.subject_id, s.key.metric) for s in series if s.quality.analyzed_count > 0}
    subjects = sorted({o.subject_id for o in accepted})
    missing = [
        MissingSeries(subject_id=subj, metric=m)
        for subj in subjects
        for m in cfg.expected_metrics
        if (subj, m) not in analyzed_pairs
    ]

    return AnalysisReport(
        config=cfg,
        input_count=len(obs),
        analyzed_count=sum(s.quality.analyzed_count for s in series),
        excluded=excluded,
        series=series,
        missing_series=missing,
    )


def _provenance_digest(origin: DataOrigin, members: Sequence[HealthObservation]) -> ProvenanceDigest:
    def distinct(attr: str) -> list[str]:
        return sorted({str(v) for o in members if (v := getattr(o.provenance, attr)) is not None})

    return ProvenanceDigest(
        data_origin=origin,
        sources=distinct("source"),
        source_refs=distinct("source_ref"),
        methods=distinct("method"),
        generator_versions=distinct("generator_version"),
    )


def _analyze_series(
    key_values: dict, part: pd.DataFrame, by_id: dict[str, HealthObservation], cfg: AnalysisConfig
) -> SeriesAnalysis:
    origin = DataOrigin(key_values["data_origin"])
    key = SeriesKey(
        subject_id=key_values["subject_id"],
        metric=key_values["metric"],
        unit=key_values["unit"],
        data_origin=origin,
        device_id=key_values["device_id"] or None,
        context=json.loads(key_values["context"]),
    )
    members = [by_id[i] for i in part["id"]]
    warnings: list[str] = []

    used = part[part["exclusion"] == ""].reset_index(drop=True)
    t = used["t"].to_numpy(dtype=float)
    values = used["value"].to_numpy(dtype=float)
    ids = used["id"].tolist()

    def at(i: int):
        return by_id[ids[i]].observed_at

    # --- quality / missingness
    if cfg.expected_interval_s.get(key.metric) is not None:
        interval, interval_source = cfg.expected_interval_s[key.metric], "configured"
    else:
        interval = calc.median_interval(t) if t.size else None
        interval_source = "inferred" if interval else None
        if interval is None:
            warnings.append(
                "fewer than 2 distinct timestamps: sampling interval, gaps and coverage undefined"
            )
    gaps: list[GapInfo] = []
    expected = coverage = None
    if interval:
        distinct_t = np.unique(t)
        first_at = {}
        for i, ti in enumerate(t):
            first_at.setdefault(ti, i)
        for g in calc.find_gaps(t, interval, cfg.gap_factor):
            gaps.append(
                GapInfo(
                    after=at(first_at[distinct_t[g.start_index]]),
                    before=at(first_at[distinct_t[g.end_index]]),
                    duration_s=g.duration_s,
                )
            )
        expected = calc.expected_count(t, interval)
        coverage = calc.coverage_fraction(t, interval)
    duplicates = calc.count_duplicate_times(t) if t.size else 0
    if duplicates:
        warnings.append(f"{duplicates} observation(s) share a timestamp with another in this series")

    quality = DataQualityReport(
        total_count=len(part),
        analyzed_count=len(used),
        excluded_counts=dict(sorted(Counter(e for e in part["exclusion"] if e).items())),
        quality_counts=dict(sorted(Counter(part["quality"]).items())),
        duplicate_timestamps=duplicates,
        expected_interval_s=interval,
        interval_source=interval_source,
        expected_count=expected,
        coverage_fraction=coverage,
        gaps=gaps,
    )

    descriptive = _stats_model(calc.describe(values)) if values.size else None
    if descriptive is None:
        warnings.append("no analysable observations in this series")

    # --- baseline, deviations, anomalies
    baseline = latest = None
    deviations: list[Deviation] = []
    anomalies: list[AnomalyFlag] = []
    spec = cfg.baseline
    if values.size:
        if spec.mode == "first_n":
            mask = calc.first_n_mask(values.size, spec.n)
            post = np.arange(values.size) >= spec.n
        else:
            mask = calc.window_mask(t, spec.start.timestamp(), spec.end.timestamp())
            post = t >= spec.end.timestamp()
        n_base = int(mask.sum())
        if n_base < spec.min_count:
            warnings.append(
                f"baseline has {n_base} value(s); at least {spec.min_count} needed for deviations"
            )
        else:
            base_idx = np.flatnonzero(mask)
            b = calc.describe(values[mask])
            baseline = BaselineSummary(
                mode=spec.mode,
                count=n_base,
                start=at(int(base_idx[0])),
                end=at(int(base_idx[-1])),
                stats=_stats_model(b),
            )
            if b.mad == 0:
                warnings.append(
                    "baseline MAD is zero: modified z-scores undefined, no anomaly flags possible"
                )
            post_idx = np.flatnonzero(post)
            if post_idx.size == 0:
                warnings.append("no observations after the baseline to compare")
            else:
                dev = calc.deviations_from_baseline(values[post_idx], b)
                flags = calc.flag_modified_z(dev.modified_z, cfg.modified_z_cutoff)
                rows = [
                    Deviation(
                        observation_id=ids[i],
                        observed_at=at(i),
                        value=float(values[i]),
                        delta_from_baseline_median=float(dev.delta[j]),
                        z=_finite_or_none(dev.z[j]),
                        modified_z=_finite_or_none(dev.modified_z[j]),
                    )
                    for j, i in enumerate(post_idx)
                ]
                latest = rows[-1]
                if cfg.include_point_deviations:
                    deviations = rows
                anomalies = [
                    AnomalyFlag(
                        observation_id=rows[j].observation_id,
                        observed_at=rows[j].observed_at,
                        value=rows[j].value,
                        unit=key.unit,
                        data_origin=origin,
                        modified_z=float(dev.modified_z[j]),
                        method=ANOMALY_METHOD,
                        cutoff=cfg.modified_z_cutoff,
                    )
                    for j in np.flatnonzero(flags)
                ]

    return SeriesAnalysis(
        key=key,
        provenance=_provenance_digest(origin, members),
        first_observed_at=members[0].observed_at,
        last_observed_at=members[-1].observed_at,
        descriptive=descriptive,
        baseline=baseline,
        latest_deviation=latest,
        deviations=deviations,
        anomalies=anomalies,
        quality=quality,
        warnings=warnings,
    )
