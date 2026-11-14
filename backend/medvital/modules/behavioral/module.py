"""Behavioral health module: sleep duration and a self-reported stress score.

``self_reported_stress`` uses a plain 0-10 placeholder scale. It is NOT a validated clinical
instrument and no cut-offs are defined for it.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from medvital.core.derive import make_modeled
from medvital.core.metrics import DERIVED_ORIGINS, MetricSpec
from medvital.core.module import HealthModule
from medvital.core.observation import HealthObservation, ModuleId
from medvital.core.provenance import DataOrigin
from medvital.modules.behavioral.calculations import trailing_mean

SLEEP = "sleep_duration"
STRESS = "self_reported_stress"
SLEEP_MEAN = "sleep_duration_7d_mean"
SLEEP_MEAN_METHOD = "trailing_mean_of_last_7_samples_v1"
WINDOW = 7

METRICS = (
    MetricSpec(
        name=SLEEP,
        unit="h",
        description="Sleep duration per day.",
        physical_min=0.0,
        physical_max=24.0,
    ),
    MetricSpec(
        name=STRESS,
        unit="score_0_10",
        description="Self-reported stress on a plain 0-10 placeholder scale (not a validated "
        "instrument).",
        physical_min=0.0,
        physical_max=10.0,
    ),
    MetricSpec(
        name=SLEEP_MEAN,
        unit="h",
        description="Mean of the most recent 7 sleep-duration samples (modeled).",
        allowed_origins=DERIVED_ORIGINS,
    ),
)


def derive(observations: Sequence[HealthObservation]) -> list[HealthObservation]:
    groups: dict[tuple[str, DataOrigin], list[HealthObservation]] = defaultdict(list)
    for o in observations:
        if (
            o.module is ModuleId.BEHAVIORAL
            and o.metric == SLEEP
            and o.provenance.origin is not DataOrigin.MODELED
        ):
            groups[(o.astronaut_id, o.provenance.origin)].append(o)

    out: list[HealthObservation] = []
    for (astronaut_id, origin), items in sorted(groups.items(), key=lambda kv: str(kv[0])):
        items.sort(key=lambda o: (o.observed_at, str(o.id)))
        if len(items) < WINDOW:
            continue
        window = items[-WINDOW:]
        out.append(
            make_modeled(
                module=ModuleId.BEHAVIORAL,
                astronaut_id=astronaut_id,
                metric=SLEEP_MEAN,
                value=trailing_mean([o.value for o in window], WINDOW),
                unit="h",
                observed_at=window[-1].observed_at,
                method=SLEEP_MEAN_METHOD,
                inputs=window,
                context={"input_origin": origin.value},
            )
        )
    return out


MODULE = HealthModule(
    id=ModuleId.BEHAVIORAL,
    title="Behavioral health",
    description="Sleep duration and a self-reported stress score.",
    metrics=METRICS,
    derive=derive,
)
