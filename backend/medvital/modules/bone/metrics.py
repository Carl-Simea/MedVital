from medvital.core.module_spec import MetricDefinition
from medvital.core.schema import ModuleId

AREAL_BMD = "bone.areal_bmd"
EXERCISE_DURATION = "bone.countermeasure_exercise_duration"

METRICS = (
    MetricDefinition(
        metric=EXERCISE_DURATION,
        module=ModuleId.BONE,
        unit="min",
        description=(
            "Duration of one countermeasure exercise session. Activity logging only: a wearable "
            "does not measure bone density."
        ),
        non_negative=True,
        optional_context=("activity", "device"),
    ),
    MetricDefinition(
        metric=AREAL_BMD,
        module=ModuleId.BONE,
        unit="g/cm2",
        description="Areal bone mineral density at a named skeletal site (e.g. from DXA).",
        non_negative=True,
        optional_context=("site", "device"),
    ),
)
