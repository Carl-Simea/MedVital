"""Bone module: observations -> ModuleSummary."""

from __future__ import annotations

from collections.abc import Sequence

from medvital.core.frame import group_series
from medvital.core.schema import HealthObservation, ModuleId
from medvital.core.stats import fit_linear_trend
from medvital.core.summary import DerivedValue, ModuleSummary, summarize_metric
from medvital.modules.bone import calculations as calc
from medvital.modules.bone.metrics import AREAL_BMD

METHOD_PCT = "percent change of latest value vs earliest value in the same series v1"
METHOD_TREND = "ordinary least squares of value vs elapsed days (scipy.stats.linregress) v1"
# Series are separated per skeletal site and per data origin; they are never pooled.
CONTEXT_KEYS = ("site", "device")


def summarize(subject_id: str, observations: Sequence[HealthObservation]) -> ModuleSummary:
    mine = [o for o in observations if o.module is ModuleId.BONE and o.subject_id == subject_id]
    derived: list[DerivedValue] = []
    warnings: list[str] = []

    for group in group_series(mine, AREAL_BMD, CONTEXT_KEYS):
        values = group.frame["value"].to_numpy()
        label = f"{AREAL_BMD} [{group.data_origin.value}] {group.context}"
        common = dict(
            input_metric=AREAL_BMD,
            input_origin=group.data_origin,
            input_count=len(values),
            context=group.context,
        )
        if len(values) >= 2:
            try:
                pct = calc.percent_change_from_baseline(float(values[0]), float(values[-1]))
            except ValueError:
                warnings.append(f"{label}: baseline is not > 0; percent change skipped.")
            else:
                derived.append(
                    DerivedValue(
                        name="percent_change_from_first_observation",
                        description="Change of the latest value relative to the first value in the series.",
                        value=pct,
                        unit="%",
                        method=METHOD_PCT,
                        **common,
                    )
                )
        else:
            warnings.append(f"{label}: needs >= 2 observations for percent change.")

        fit = fit_linear_trend(group.frame["days"].to_numpy(), values)
        if fit is None:
            warnings.append(f"{label}: needs >= 3 observations at distinct times for a trend.")
        else:
            derived.append(
                DerivedValue(
                    name="trend_slope_per_day",
                    description="Least-squares slope. Descriptive of the supplied points; not a forecast.",
                    value=fit.slope_per_day,
                    unit="g/cm2/d",
                    method=METHOD_TREND,
                    **common,
                )
            )

    return ModuleSummary(
        module=ModuleId.BONE,
        subject_id=subject_id,
        observation_count=len(mine),
        metric_summaries=summarize_metric(mine, AREAL_BMD, CONTEXT_KEYS),
        derived_values=derived,
        warnings=warnings,
    )
