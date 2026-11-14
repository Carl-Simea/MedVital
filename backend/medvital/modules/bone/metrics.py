from medvital.core.module_spec import MetricDefinition
from medvital.core.schema import ModuleId

AREAL_BMD = "bone.areal_bmd"

METRICS = (
    MetricDefinition(
        metric=AREAL_BMD,
        module=ModuleId.BONE,
        unit="g/cm2",
        description="Areal bone mineral density at a named skeletal site (e.g. from DXA).",
        non_negative=True,
        optional_context=("site", "device"),
    ),
)
