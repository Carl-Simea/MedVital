"""Radiation module: observations -> ModuleSummary. Adapter only; maths is in calculations."""

from __future__ import annotations

from collections.abc import Sequence

from medvital.core.frame import group_series
from medvital.core.schema import HealthObservation, ModuleId
from medvital.core.summary import DerivedValue, ModuleSummary, summarize_metric
from medvital.modules.radiation import calculations as calc
from medvital.modules.radiation.metrics import DAILY_METRICS, METRICS

METHOD_CUMULATIVE = "sum of supplied daily values (radiation.calculations.cumulative_dose) v1"
METHOD_MEAN = "arithmetic mean of supplied daily values v1"


def summarize(subject_id: str, observations: Sequence[HealthObservation]) -> ModuleSummary:
    mine = [o for o in observations if o.module is ModuleId.RADIATION and o.subject_id == subject_id]
    summaries = []
    derived: list[DerivedValue] = []
    warnings: list[str] = []

    for definition in METRICS:
        summaries.extend(summarize_metric(mine, definition.metric))
        if definition.metric not in DAILY_METRICS:
            continue  # e.g. dose_rate: descriptive statistics only; summing rates would be meaningless
        for group in group_series(mine, definition.metric):
            values = group.frame["value"].to_numpy()
            days = group.frame["observed_at"].dt.strftime("%Y%m%d").astype(int).to_numpy()
            dupes = calc.count_duplicate_days(days)
            if dupes:
                warnings.append(
                    f"{definition.metric} [{group.data_origin.value}]: {dupes} observation(s) share a "
                    "day with another; cumulative dose may double-count."
                )
            derived.append(
                DerivedValue(
                    name="cumulative_dose_over_observed_days",
                    description="Sum of supplied daily values. Days without observations are not imputed.",
                    value=float(calc.cumulative_dose(values)[-1]),
                    unit=group.unit,
                    method=METHOD_CUMULATIVE,
                    input_metric=definition.metric,
                    input_origin=group.data_origin,
                    input_count=len(values),
                )
            )
            derived.append(
                DerivedValue(
                    name="mean_daily_dose",
                    description="Arithmetic mean of supplied daily values.",
                    value=calc.mean_daily_dose(values),
                    unit=f"{group.unit}/d",
                    method=METHOD_MEAN,
                    input_metric=definition.metric,
                    input_origin=group.data_origin,
                    input_count=len(values),
                )
            )

    return ModuleSummary(
        module=ModuleId.RADIATION,
        subject_id=subject_id,
        observation_count=len(mine),
        metric_summaries=summaries,
        derived_values=derived,
        warnings=warnings,
    )
