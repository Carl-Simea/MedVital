"""Behavioral module: observations -> ModuleSummary."""

from __future__ import annotations

from collections.abc import Sequence

from medvital.core.frame import group_series
from medvital.core.schema import HealthObservation, ModuleId
from medvital.core.summary import DerivedValue, ModuleSummary, summarize_metric
from medvital.modules.behavioral import calculations as calc
from medvital.modules.behavioral.metrics import METRICS, SELF_REPORT_SCORE

METHOD_DEVIATION = (
    "RobustScaler (median/IQR) fitted on the first N values of the same series; "
    "latest value transformed v1"
)


def summarize(
    subject_id: str,
    observations: Sequence[HealthObservation],
    baseline_window: int = calc.DEFAULT_BASELINE_WINDOW,
) -> ModuleSummary:
    mine = [o for o in observations if o.module is ModuleId.BEHAVIORAL and o.subject_id == subject_id]
    summaries = []
    derived: list[DerivedValue] = []
    warnings: list[str] = []

    for definition in METRICS:
        # Self-report scores are separated per instrument; sleep per device.
        keys = ("instrument",) if definition.metric == SELF_REPORT_SCORE else ("device",)
        summaries.extend(summarize_metric(mine, definition.metric, keys))
        for group in group_series(mine, definition.metric, keys):
            values = group.frame["value"].to_numpy()
            label = f"{definition.metric} [{group.data_origin.value}] {group.context}"
            try:
                deviations = calc.robust_deviation_from_baseline(values, baseline_window)
            except ValueError:
                warnings.append(
                    f"{label}: needs more than {baseline_window} observations for a baseline deviation."
                )
                continue
            derived.append(
                DerivedValue(
                    name="latest_deviation_from_own_baseline",
                    description=(
                        f"(latest - median) / IQR of the subject's first {baseline_window} values. "
                        "Position relative to the subject's own history, not a clinical score."
                    ),
                    value=float(deviations[-1]),
                    unit="{IQR_from_baseline_median}",
                    method=METHOD_DEVIATION,
                    input_metric=definition.metric,
                    input_origin=group.data_origin,
                    input_count=len(values),
                    context=group.context,
                )
            )

    return ModuleSummary(
        module=ModuleId.BEHAVIORAL,
        subject_id=subject_id,
        observation_count=len(mine),
        metric_summaries=summaries,
        derived_values=derived,
        warnings=warnings,
    )
