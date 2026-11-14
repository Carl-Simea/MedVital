"""Radiation module: observations -> ModuleSummary. Adapter only; maths is in calculations."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from medvital.core.frame import group_series
from medvital.core.schema import HealthObservation, ModuleId
from medvital.core.summary import DerivedValue, ModuleSummary, summarize_metric
from medvital.modules.radiation import calculations as calc
from medvital.modules.radiation.metrics import DAILY_METRICS, DOSE_RATE, METRICS

METHOD_CUMULATIVE = "sum of supplied daily values (radiation.calculations.cumulative_dose) v1"
METHOD_MEAN = "arithmetic mean of supplied daily values v1"
METHOD_RATE_INTEGRAL = (
    "piecewise-constant (left-point) integration of dose-rate samples over intervals <= 2x the median "
    "sampling interval; longer gaps are not integrated (radiation.calculations.dose_from_constant_rate) v1"
)


def _integrate_rates(
    mine: Sequence[HealthObservation], derived: list[DerivedValue], warnings: list[str]
) -> None:
    """Personal dosimeter dose-rate samples -> integrated dose over sampled intervals (modeled).

    Not applicable to environmental detectors: those are EnvironmentalEvent records, never observations.
    """
    for group in group_series(mine, DOSE_RATE, ("instrument",)):
        frame = group.frame
        label = f"{DOSE_RATE} [{group.data_origin.value}] {group.context}"
        if len(frame) < 2:
            warnings.append(f"{label}: needs >= 2 samples for rate integration.")
            continue
        seconds = frame["days"].to_numpy() * 86400.0  # resolution-independent elapsed time
        gaps = seconds[1:] - seconds[:-1]
        positive = gaps[gaps > 0]
        if positive.size == 0:
            warnings.append(f"{label}: all samples share one timestamp; no integration.")
            continue
        max_gap = 2.0 * float(np.median(positive))
        total, unit, skipped = 0.0, None, 0.0
        rates = frame["value"].to_numpy()
        for rate, gap in zip(rates[:-1], gaps, strict=True):
            if gap <= 0:
                continue
            if gap > max_gap:
                skipped += gap
                continue
            dose, unit = calc.dose_from_constant_rate(float(rate), rate_unit=group.unit, elapsed_s=float(gap))
            total += dose
        if unit is None:
            warnings.append(f"{label}: no interval short enough to integrate.")
            continue
        if skipped:
            warnings.append(f"{label}: {skipped / 3600:.2f} h in long gaps not integrated (lower bound).")
        derived.append(
            DerivedValue(
                name="integrated_dose_over_sampled_intervals",
                description=(
                    "Dose from a personal dose-rate series assuming each rate holds until the next sample; "
                    "gaps longer than 2x the median interval are excluded, so this is a lower bound."
                ),
                value=total,
                unit=unit,
                method=METHOD_RATE_INTEGRAL,
                input_metric=DOSE_RATE,
                input_origin=group.data_origin,
                input_count=len(frame),
                context=group.context,
            )
        )


def summarize(subject_id: str, observations: Sequence[HealthObservation]) -> ModuleSummary:
    mine = [o for o in observations if o.module is ModuleId.RADIATION and o.subject_id == subject_id]
    summaries = []
    derived: list[DerivedValue] = []
    warnings: list[str] = []

    for definition in METRICS:
        summaries.extend(summarize_metric(mine, definition.metric))
        if definition.metric == DOSE_RATE:
            _integrate_rates(mine, derived, warnings)
            continue
        if definition.metric not in DAILY_METRICS:
            continue
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
