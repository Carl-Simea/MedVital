"""Bone health module: areal bone mineral density and change from a person's own baseline."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from medvital.core.derive import make_modeled
from medvital.core.metrics import DERIVED_ORIGINS, MetricSpec
from medvital.core.module import HealthModule
from medvital.core.observation import HealthObservation, ModuleId
from medvital.core.provenance import DataOrigin
from medvital.modules.bone.calculations import percent_change

BMD = "bmd_areal"
BMD_CHANGE = "bmd_percent_change_from_baseline"
CHANGE_METHOD = "percent_change_from_first_observation_v1"

METRICS = (
    MetricSpec(
        name=BMD,
        unit="g/cm2",
        description="Areal bone mineral density at a named site (context key 'site').",
        physical_min=0.0,
        sim_cadence_days=30,
    ),
    MetricSpec(
        name=BMD_CHANGE,
        unit="percent",
        description="Change from the person's own first observation at the same site (modeled).",
        allowed_origins=DERIVED_ORIGINS,
    ),
)


def derive(observations: Sequence[HealthObservation]) -> list[HealthObservation]:
    groups: dict[tuple[str, DataOrigin, str], list[HealthObservation]] = defaultdict(list)
    for o in observations:
        if (
            o.module is ModuleId.BONE
            and o.metric == BMD
            and o.provenance.origin is not DataOrigin.MODELED
        ):
            groups[
                (o.astronaut_id, o.provenance.origin, o.context.get("site", "unspecified"))
            ].append(o)

    out: list[HealthObservation] = []
    for (astronaut_id, origin, site), items in sorted(groups.items(), key=lambda kv: str(kv[0])):
        items.sort(key=lambda o: (o.observed_at, str(o.id)))
        first, last = items[0], items[-1]
        if len(items) < 2 or first.observed_at == last.observed_at or first.value <= 0:
            continue
        out.append(
            make_modeled(
                module=ModuleId.BONE,
                astronaut_id=astronaut_id,
                metric=BMD_CHANGE,
                value=percent_change(first.value, last.value),
                unit="percent",
                observed_at=last.observed_at,
                method=CHANGE_METHOD,
                inputs=[first, last],
                context={"site": site, "input_origin": origin.value},
            )
        )
    return out


MODULE = HealthModule(
    id=ModuleId.BONE,
    title="Bone health",
    description="Areal bone mineral density and change from the person's own baseline.",
    metrics=METRICS,
    derive=derive,
    sim_context={"site": "simulated_site"},
)
