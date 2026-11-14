"""Behavioral module: observations -> ModuleSummary."""

from __future__ import annotations

from collections.abc import Sequence

from medvital.core.frame import group_series
from medvital.core.pairing import pair_observations
from medvital.core.schema import HealthObservation, ModuleId
from medvital.core.summary import DerivedValue, ModuleSummary, summarize_metric
from medvital.modules.behavioral import calculations as calc
from medvital.modules.behavioral.metrics import METRICS, SELF_REPORT_SCORE, SLEEP_DURATION, TIME_IN_BED

METHOD_SE = "sleep efficiency TST/TIB x 100 (Hand & Siengsukon 2025, doi:10.1093/sleepadvances/zpaf045) v1"
METHOD_DEVIATION = (
    "RobustScaler (median/IQR) fitted on the first N values of the same series; latest value transformed v1"
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
        keys = {
            SELF_REPORT_SCORE: ("instrument",),
            TIME_IN_BED: ("tib_definition", "device"),
        }.get(definition.metric, ("device",))
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

    # Sleep efficiency: only from a sleep-duration + time-in-bed pair of the same sleep period
    # (same device, origin and time). The TIB definition travels with the result; never pooled.
    paired = pair_observations(mine, SLEEP_DURATION, TIME_IN_BED)
    if paired.ambiguous:
        warnings.append(f"sleep_efficiency: {paired.ambiguous} observation(s) skipped as ambiguous pairs.")
    latest: dict[tuple, object] = {}
    for p in paired.pairs:
        latest[(p.a.provenance.data_origin, p.a.device_id, p.b.context["tib_definition"])] = p
    for (origin, device, tib_definition), p in sorted(latest.items(), key=lambda kv: str(kv[0])):
        try:
            value = calc.sleep_efficiency(
                p.a.value, p.b.value, unit=p.a.unit if p.a.unit == p.b.unit else "?"
            )
        except ValueError as exc:
            warnings.append(f"sleep_efficiency [{origin.value}]: {exc}")
            continue
        context = {"tib_definition": tib_definition, **({"device": device} if device else {})}
        derived.append(
            DerivedValue(
                name="sleep_efficiency",
                description="Total sleep time / time in bed x 100 for one sleep period. No cut-off applied.",
                value=value,
                unit="%",
                method=METHOD_SE,
                input_metric=f"{SLEEP_DURATION}+{TIME_IN_BED}",
                input_origin=origin,
                input_count=len(paired.pairs),
                context=context,
                observed_at=p.a.observed_at,
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
