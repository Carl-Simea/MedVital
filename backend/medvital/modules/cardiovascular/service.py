"""Cardiovascular module: observations -> ModuleSummary."""

from __future__ import annotations

from collections.abc import Sequence

from medvital.core.frame import group_series
from medvital.core.schema import HealthObservation, ModuleId
from medvital.core.summary import DerivedValue, ModuleSummary, summarize_metric
from medvital.modules.cardiovascular import calculations as calc
from medvital.modules.cardiovascular.metrics import METRICS, RR_INTERVAL

METHOD_RMSSD = "RMSSD of successive RR-interval differences, no artefact correction v1"


def summarize(subject_id: str, observations: Sequence[HealthObservation]) -> ModuleSummary:
    mine = [
        o for o in observations if o.module is ModuleId.CARDIOVASCULAR and o.subject_id == subject_id
    ]
    summaries = []
    for definition in METRICS:
        if definition.metric == RR_INTERVAL:
            continue  # individual beats are summarised per recording below, not as a pooled series
        # Series are split by every declared qualifier (e.g. device, posture) — never pooled.
        summaries.extend(summarize_metric(mine, definition.metric, definition.optional_context))

    derived: list[DerivedValue] = []
    warnings: list[str] = []
    # One RMSSD per (data origin, recording session). Sessions are never pooled.
    for group in group_series(mine, RR_INTERVAL, ("session_id",)):
        values = group.frame["value"].to_numpy()
        session = group.context["session_id"]
        try:
            value = calc.rmssd(values)
        except ValueError as exc:
            warnings.append(f"{RR_INTERVAL} [{group.data_origin.value}] session {session}: {exc}")
            continue
        derived.append(
            DerivedValue(
                name="rmssd",
                description="Time-domain HRV statistic for one recording session; no artefact correction.",
                value=value,
                unit="ms",
                method=METHOD_RMSSD,
                input_metric=RR_INTERVAL,
                input_origin=group.data_origin,
                input_count=len(values),
                context=group.context,
            )
        )

    return ModuleSummary(
        module=ModuleId.CARDIOVASCULAR,
        subject_id=subject_id,
        observation_count=len(mine),
        metric_summaries=summaries,
        derived_values=derived,
        warnings=warnings,
    )
