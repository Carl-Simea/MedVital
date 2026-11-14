"""Radiation module: absorbed dose rate and its accumulation."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from medvital.core.derive import make_modeled
from medvital.core.metrics import DERIVED_ORIGINS, MetricSpec
from medvital.core.module import HealthModule
from medvital.core.observation import HealthObservation, ModuleId
from medvital.core.provenance import DataOrigin
from medvital.modules.radiation.calculations import cumulative_dose

DOSE_RATE = "absorbed_dose_rate"
CUMULATIVE_DOSE = "cumulative_absorbed_dose"
CUMULATIVE_METHOD = "trapezoidal_integration_of_dose_rate_v1"

METRICS = (
    MetricSpec(
        name=DOSE_RATE,
        unit="uGy/day",
        description="Absorbed dose rate.",
        physical_min=0.0,
    ),
    MetricSpec(
        name=CUMULATIVE_DOSE,
        unit="uGy",
        description="Dose accumulated across the observed period (modeled from dose rate).",
        allowed_origins=DERIVED_ORIGINS,
    ),
)


def derive(observations: Sequence[HealthObservation]) -> list[HealthObservation]:
    groups: dict[tuple[str, DataOrigin], list[HealthObservation]] = defaultdict(list)
    for o in observations:
        if (
            o.module is ModuleId.RADIATION
            and o.metric == DOSE_RATE
            and o.provenance.origin is not DataOrigin.MODELED
        ):
            groups[(o.astronaut_id, o.provenance.origin)].append(o)

    out: list[HealthObservation] = []
    for (astronaut_id, origin), items in sorted(groups.items(), key=lambda kv: str(kv[0])):
        items.sort(key=lambda o: (o.observed_at, str(o.id)))
        first, last = items[0].observed_at, items[-1].observed_at
        if len(items) < 2 or first == last:
            continue
        times_days = [(o.observed_at - first).total_seconds() / 86400.0 for o in items]
        total = cumulative_dose(times_days, [o.value for o in items])
        out.append(
            make_modeled(
                module=ModuleId.RADIATION,
                astronaut_id=astronaut_id,
                metric=CUMULATIVE_DOSE,
                value=total,
                unit="uGy",
                observed_at=last,
                method=CUMULATIVE_METHOD,
                inputs=items,
                context={"input_origin": origin.value},
            )
        )
    return out


MODULE = HealthModule(
    id=ModuleId.RADIATION,
    title="Radiation",
    description="Absorbed dose rate and accumulated dose.",
    metrics=METRICS,
    derive=derive,
)
