"""Analysis configuration and result contract (JSON-compatible via ``model_dump(mode="json")``).

Results are descriptive and statistical. An ``AnomalyFlag`` means "statistically unusual
relative to this subject's own baseline in this series — review it", never a diagnosis.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from medvital.core.schema import DataOrigin, Quality

ANALYSIS_VERSION = "0.1.1"

ANALYSIS_NOTICE = (
    "Statistical description only. Not a diagnosis, not medical advice; no clinical thresholds "
    "are applied. Anomaly flags mark values that are statistically unusual relative to the "
    "subject's own baseline within one series, for human review. Simulated, measured and "
    "modeled values are analysed separately and never pooled."
)


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- configuration


class BaselineSpec(_Frozen):
    """How the personal baseline of each series is chosen.

    * ``first_n``: the first ``n`` analysed values of the series (time-ordered).
    * ``time_window``: values with ``start <= observed_at < end``.

    Defaults are engineering choices for exercising software, not scientific recommendations.
    """

    mode: Literal["first_n", "time_window"] = "first_n"
    n: int = Field(default=7, ge=1)
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    min_count: int = Field(default=4, ge=2, description="Fewer baseline values => no deviations.")

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.mode == "time_window":
            if self.start is None or self.end is None:
                raise ValueError("time_window baseline requires start and end")
            if not self.end > self.start:
                raise ValueError("baseline end must be after start")
        return self


class AnalysisConfig(_Frozen):
    baseline: BaselineSpec = Field(default_factory=BaselineSpec)
    modified_z_cutoff: float = Field(
        default=3.5,
        gt=0,
        description="Statistical outlier cutoff on |modified z| (Iglewicz & Hoaglin 1993 convention). "
        "Not a clinical threshold.",
    )
    gap_factor: float = Field(
        default=2.0, ge=1, description="Spacing > gap_factor * expected interval = gap."
    )
    expected_interval_s: dict[str, float] = Field(
        default_factory=dict,
        description="Expected sampling interval per metric id (seconds). Missing => inferred from the "
        "series' median spacing and labelled 'inferred'.",
    )
    expected_metrics: tuple[str, ...] = Field(
        default=(), description="Metric ids every subject is expected to have; absences are reported."
    )
    analyzed_qualities: tuple[Quality, ...] = Field(
        default=(Quality.VALID,),
        description="Quality values included in statistics. Others are excluded and counted, never dropped.",
    )
    include_point_deviations: bool = Field(
        default=False, description="Return one deviation row per post-baseline observation."
    )

    @model_validator(mode="after")
    def _check_intervals(self) -> Self:
        for metric, seconds in self.expected_interval_s.items():
            if not seconds > 0:
                raise ValueError(f"expected interval for {metric} must be > 0")
        return self


# --------------------------------------------------------------------------- results


class ExclusionReason(StrEnum):
    SUPERSEDED = "superseded"  # a later observation in the input supersedes it
    QUALITY = "quality"  # quality not in AnalysisConfig.analyzed_qualities
    REJECTED = "rejected"  # failed registry validation


class ExcludedObservation(_Frozen):
    observation_id: str
    reason: ExclusionReason
    detail: str


class SeriesKey(_Frozen):
    """Everything that makes two values comparable. Values with different keys are never pooled."""

    subject_id: str
    metric: str
    unit: str
    data_origin: DataOrigin
    device_id: str | None = None
    context: dict[str, str] = Field(default_factory=dict)


class ProvenanceDigest(_Frozen):
    data_origin: DataOrigin
    sources: list[str]
    source_refs: list[str]
    methods: list[str]
    generator_versions: list[str]


class DescriptiveStats(_Frozen):
    count: int
    mean: float
    std: float | None
    median: float
    q1: float
    q3: float
    iqr: float
    mad: float
    minimum: float
    maximum: float


class BaselineSummary(_Frozen):
    mode: Literal["first_n", "time_window"]
    count: int
    start: datetime
    end: datetime
    stats: DescriptiveStats


class Deviation(_Frozen):
    observation_id: str
    observed_at: datetime
    value: float
    delta_from_baseline_median: float
    z: float | None
    modified_z: float | None


class AnomalyFlag(_Frozen):
    observation_id: str
    observed_at: datetime
    value: float
    unit: str
    data_origin: DataOrigin
    modified_z: float
    method: str
    cutoff: float
    note: str = "Statistically unusual relative to own baseline; for review. Not a clinical finding."


class GapInfo(_Frozen):
    after: datetime
    before: datetime
    duration_s: float


class DataQualityReport(_Frozen):
    total_count: int = Field(description="Observations in this series before exclusions.")
    analyzed_count: int
    excluded_counts: dict[str, int] = Field(description="Per ExclusionReason.")
    quality_counts: dict[str, int]
    duplicate_timestamps: int
    expected_interval_s: float | None
    interval_source: Literal["configured", "inferred"] | None
    expected_count: int | None
    coverage_fraction: float | None = Field(description="Distinct timestamps / expected, capped at 1.")
    gaps: list[GapInfo]


class SeriesAnalysis(_Frozen):
    key: SeriesKey
    provenance: ProvenanceDigest
    first_observed_at: datetime
    last_observed_at: datetime
    descriptive: DescriptiveStats | None
    baseline: BaselineSummary | None
    latest_deviation: Deviation | None
    deviations: list[Deviation] = Field(default_factory=list)
    anomalies: list[AnomalyFlag]
    quality: DataQualityReport
    warnings: list[str]


class MissingSeries(_Frozen):
    subject_id: str
    metric: str


class AnalysisReport(_Frozen):
    analysis_version: str = ANALYSIS_VERSION
    notice: str = ANALYSIS_NOTICE
    config: AnalysisConfig
    input_count: int
    analyzed_count: int
    excluded: list[ExcludedObservation]
    series: list[SeriesAnalysis]
    missing_series: list[MissingSeries]
