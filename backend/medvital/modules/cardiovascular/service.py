"""Cardiovascular module: observations -> ModuleSummary."""

from __future__ import annotations

from collections.abc import Sequence

from medvital.core.frame import group_series
from medvital.core.pairing import pair_observations
from medvital.core.schema import HealthObservation, ModuleId
from medvital.core.summary import DerivedValue, ModuleSummary, summarize_metric
from medvital.modules.cardiovascular import calculations as calc
from medvital.modules.cardiovascular.metrics import (
    DIASTOLIC_BP,
    HEART_RATE,
    METRICS,
    RR_INTERVAL,
    STROKE_VOLUME,
    SYSTOLIC_BP,
)

METHOD_RMSSD = "RMSSD of successive RR-interval differences, no artefact correction v1"
METHOD_MAP = "MAP estimate DBP + (SBP - DBP)/3 from one paired reading; uncited approximation (G-7) v1"
METHOD_CO = "cardiac output HR * SV / 1000 from one paired event (same device, time, origin) v1"


def summarize(subject_id: str, observations: Sequence[HealthObservation]) -> ModuleSummary:
    mine = [o for o in observations if o.module is ModuleId.CARDIOVASCULAR and o.subject_id == subject_id]
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

    # Paired derived values: latest pair per (origin, device, context), never across events.
    for metric_a, metric_b, keys, name, method in (
        (SYSTOLIC_BP, DIASTOLIC_BP, ("posture",), "mean_arterial_pressure_estimate", METHOD_MAP),
        (HEART_RATE, STROKE_VOLUME, ("posture",), "cardiac_output", METHOD_CO),
    ):
        paired = pair_observations(mine, metric_a, metric_b, keys)
        if paired.ambiguous:
            warnings.append(f"{name}: {paired.ambiguous} observation(s) skipped as ambiguous pairs.")
        latest: dict[tuple, object] = {}
        for p in paired.pairs:
            latest[
                (p.a.provenance.data_origin, p.a.device_id, tuple(p.a.context.get(k, "") for k in keys))
            ] = p
        for (origin, device, ctx), p in sorted(latest.items(), key=lambda kv: str(kv[0])):
            context = {k: v for k, v in zip(keys, ctx, strict=True) if v}
            if device:
                context["device"] = device
            try:
                if name == "cardiac_output":
                    value = calc.cardiac_output(
                        p.a.value, p.b.value, heart_rate_unit=p.a.unit, stroke_volume_unit=p.b.unit
                    )
                    unit, desc = calc.CARDIAC_OUTPUT_UNIT, "Cardiac output from one paired HR + SV event."
                else:
                    value = calc.mean_arterial_pressure_estimate(p.a.value, p.b.value, unit=p.a.unit)
                    unit = calc.PRESSURE_UNIT
                    desc = (
                        "Estimated MAP from one paired SBP/DBP reading (approximation; not a measured MAP)."
                    )
            except ValueError as exc:
                warnings.append(f"{name} [{origin.value}]: {exc}")
                continue
            derived.append(
                DerivedValue(
                    name=name,
                    description=desc,
                    value=value,
                    unit=unit,
                    method=method,
                    input_metric=f"{metric_a}+{metric_b}",
                    input_origin=origin,
                    input_count=len(paired.pairs),
                    context=context,
                    observed_at=p.a.observed_at,
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
