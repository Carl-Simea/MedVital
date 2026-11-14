"""Bone module: observations -> ModuleSummary."""

from __future__ import annotations

from collections.abc import Sequence

from medvital.core.frame import group_series
from medvital.core.schema import HealthObservation, ModuleId
from medvital.core.stats import fit_linear_trend, percent_change
from medvital.core.summary import DerivedValue, ModuleSummary, summarize_metric
from medvital.modules.bone.metrics import AREAL_BMD, EXERCISE_DURATION, VOLUMETRIC_BMD

METHOD_PCT = "percent change of latest vs earliest value in the same series, first-order uncertainty v2"
METHOD_TREND = "ordinary least squares of value vs elapsed days (scipy.stats.linregress) v1"
# Series are separated per skeletal site and per data origin; they are never pooled.
CONTEXT_KEYS = ("site", "device")
VOLUMETRIC_CONTEXT_KEYS = ("site", "compartment", "device")


def _bmd_derived(
    mine: Sequence[HealthObservation], metric: str, context_keys: tuple[str, ...], trend_unit: str
) -> tuple[list[DerivedValue], list[str]]:
    derived: list[DerivedValue] = []
    warnings: list[str] = []
    for group in group_series(mine, metric, context_keys):
        values = group.frame["value"].to_numpy()
        label = f"{metric} [{group.data_origin.value}] {group.context}"
        common = dict(
            input_metric=metric,
            input_origin=group.data_origin,
            input_count=len(values),
            context=group.context,
        )
        if len(values) >= 2:
            by_id = {str(o.id): o for o in mine}
            first = by_id[group.frame["id"].iloc[0]]
            last = by_id[group.frame["id"].iloc[-1]]
            try:
                change = percent_change(last.value, first.value, last.uncertainty, first.uncertainty)
            except ValueError:
                warnings.append(
                    f"{label}: baseline is not usable (zero or non-finite); percent change skipped."
                )
            else:
                derived.append(
                    DerivedValue(
                        name="percent_change_from_first_observation",
                        description=(
                            "Change of the latest value relative to the first value in the same series. "
                            "Uncertainty is propagated only when both input uncertainties are known."
                        ),
                        value=change.value,
                        unit="%",
                        method=METHOD_PCT,
                        uncertainty=change.uncertainty,
                        observed_at=last.observed_at,
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
                    unit=trend_unit,
                    method=METHOD_TREND,
                    **common,
                )
            )
    return derived, warnings


def summarize(subject_id: str, observations: Sequence[HealthObservation]) -> ModuleSummary:
    mine = [o for o in observations if o.module is ModuleId.BONE and o.subject_id == subject_id]
    d1, w1 = _bmd_derived(mine, AREAL_BMD, CONTEXT_KEYS, "g/cm2/d")
    d2, w2 = _bmd_derived(mine, VOLUMETRIC_BMD, VOLUMETRIC_CONTEXT_KEYS, "mg/cm3/d")
    return ModuleSummary(
        module=ModuleId.BONE,
        subject_id=subject_id,
        observation_count=len(mine),
        metric_summaries=[
            *summarize_metric(mine, AREAL_BMD, CONTEXT_KEYS),
            *summarize_metric(mine, VOLUMETRIC_BMD, VOLUMETRIC_CONTEXT_KEYS),
            *summarize_metric(mine, EXERCISE_DURATION, ("activity", "device")),
        ],
        derived_values=[*d1, *d2],
        warnings=[*w1, *w2],
    )
