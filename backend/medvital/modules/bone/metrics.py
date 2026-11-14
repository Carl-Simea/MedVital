from medvital.core.module_spec import MetricDefinition
from medvital.core.schema import ModuleId

AREAL_BMD = "bone.areal_bmd"
VOLUMETRIC_BMD = "bone.volumetric_bmd"
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
        description=(
            "Areal bone mineral density (DXA) at a named skeletal site. Areal (DXA, g/cm2) and volumetric "
            "(QCT, mg/cm3) BMD are different quantities from different methods and are separate metrics."
        ),
        non_negative=True,
        optional_context=("site", "device"),
    ),
    MetricDefinition(
        metric=VOLUMETRIC_BMD,
        module=ModuleId.BONE,
        unit="mg/cm3",
        description=(
            "Volumetric bone mineral density (QCT) at a named skeletal site and compartment. Never pooled "
            "with areal (DXA) BMD."
        ),
        non_negative=True,
        optional_context=("site", "compartment", "device"),
    ),
)
