"""Cardiovascular module: heart rate, heart rate variability and blood pressure."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from medvital.core.derive import make_modeled
from medvital.core.metrics import DERIVED_ORIGINS, MetricSpec
from medvital.core.module import HealthModule
from medvital.core.observation import HealthObservation, ModuleId
from medvital.core.provenance import DataOrigin
from medvital.modules.cardiovascular.calculations import mean_arterial_pressure

HEART_RATE = "heart_rate"
SYSTOLIC = "systolic_bp"
DIASTOLIC = "diastolic_bp"
HRV_RMSSD = "hrv_rmssd"
MAP = "mean_arterial_pressure"
MAP_METHOD = "map_diastolic_plus_one_third_pulse_pressure_v1"

METRICS = (
    MetricSpec(name=HEART_RATE, unit="bpm", description="Heart rate.", physical_min=0.0),
    MetricSpec(
        name=SYSTOLIC, unit="mmHg", description="Systolic blood pressure.", physical_min=0.0
    ),
    MetricSpec(
        name=DIASTOLIC, unit="mmHg", description="Diastolic blood pressure.", physical_min=0.0
    ),
    MetricSpec(
        name=HRV_RMSSD,
        unit="ms",
        description="Heart rate variability as RMSSD of successive RR intervals.",
        physical_min=0.0,
    ),
    MetricSpec(
        name=MAP,
        unit="mmHg",
        description="Mean arterial pressure approximated from systolic and diastolic (modeled).",
        allowed_origins=DERIVED_ORIGINS,
    ),
)


def derive(observations: Sequence[HealthObservation]) -> list[HealthObservation]:
    pairs: dict[tuple[str, DataOrigin, datetime], dict[str, HealthObservation]] = defaultdict(dict)
    for o in observations:
        if (
            o.module is ModuleId.CARDIOVASCULAR
            and o.metric in (SYSTOLIC, DIASTOLIC)
            and o.provenance.origin is not DataOrigin.MODELED
        ):
            pairs[(o.astronaut_id, o.provenance.origin, o.observed_at)].setdefault(o.metric, o)

    out: list[HealthObservation] = []
    for (astronaut_id, origin, observed_at), by_metric in sorted(
        pairs.items(), key=lambda kv: (kv[0][0], kv[0][1].value, kv[0][2])
    ):
        sbp, dbp = by_metric.get(SYSTOLIC), by_metric.get(DIASTOLIC)
        if sbp is None or dbp is None or sbp.value < dbp.value:
            continue
        out.append(
            make_modeled(
                module=ModuleId.CARDIOVASCULAR,
                astronaut_id=astronaut_id,
                metric=MAP,
                value=mean_arterial_pressure(sbp.value, dbp.value),
                unit="mmHg",
                observed_at=observed_at,
                method=MAP_METHOD,
                inputs=[sbp, dbp],
                context={"input_origin": origin.value},
            )
        )
    return out


MODULE = HealthModule(
    id=ModuleId.CARDIOVASCULAR,
    title="Cardiovascular health",
    description="Heart rate, heart rate variability and blood pressure.",
    metrics=METRICS,
    derive=derive,
)
