from medvital.core.module_spec import MetricDefinition
from medvital.core.schema import ModuleId

ABSORBED_DOSE_DAILY = "radiation.absorbed_dose_daily"
DOSE_EQUIVALENT_DAILY = "radiation.dose_equivalent_daily"

METRICS = (
    MetricDefinition(
        metric=ABSORBED_DOSE_DAILY,
        module=ModuleId.RADIATION,
        unit="mGy",
        description="Absorbed dose integrated over one UTC day.",
        non_negative=True,
        optional_context=("instrument",),
    ),
    MetricDefinition(
        metric=DOSE_EQUIVALENT_DAILY,
        module=ModuleId.RADIATION,
        unit="mSv",
        description="Dose equivalent integrated over one UTC day.",
        non_negative=True,
        optional_context=("instrument",),
    ),
)
