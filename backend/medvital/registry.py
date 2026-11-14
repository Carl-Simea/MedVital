"""Registry of health modules and observation validation against module metric specs.

This is the only place that imports all four modules; the modules themselves stay independent.
"""

from __future__ import annotations

from medvital.core.module import HealthModule
from medvital.core.observation import HealthObservation, ModuleId
from medvital.modules.behavioral import MODULE as BEHAVIORAL
from medvital.modules.bone import MODULE as BONE
from medvital.modules.cardiovascular import MODULE as CARDIOVASCULAR
from medvital.modules.radiation import MODULE as RADIATION

MODULES: dict[ModuleId, HealthModule] = {
    m.id: m for m in (RADIATION, BONE, CARDIOVASCULAR, BEHAVIORAL)
}


class ObservationRejected(ValueError):
    """The observation is well-formed but not valid for its module."""


def get_module(module_id: ModuleId) -> HealthModule:
    return MODULES[module_id]


def validate_observation(observation: HealthObservation) -> None:
    """Raise ObservationRejected unless metric, unit and origin match the module's spec."""
    module = MODULES.get(observation.module)
    if module is None:
        raise ObservationRejected(f"unknown module '{observation.module}'")
    spec = module.spec(observation.metric)
    if spec is None:
        raise ObservationRejected(
            f"metric '{observation.metric}' is not defined for module '{observation.module}'"
        )
    if observation.unit != spec.unit:
        raise ObservationRejected(
            f"metric '{observation.metric}' must use unit '{spec.unit}', got '{observation.unit}'"
        )
    if observation.provenance.origin not in spec.allowed_origins:
        allowed = ", ".join(sorted(o.value for o in spec.allowed_origins))
        raise ObservationRejected(f"metric '{observation.metric}' only accepts origin: {allowed}")
