from medvital.core.module_spec import MetricDefinition
from medvital.core.schema import ModuleId

DOSE_RATE = "radiation.dose_rate"
ABSORBED_DOSE_DAILY = "radiation.absorbed_dose_daily"
DOSE_EQUIVALENT_DAILY = "radiation.dose_equivalent_daily"
DOSE_EQUIVALENT_RATE = "radiation.dose_equivalent_rate"
CUMULATIVE_DOSE_EQUIVALENT = "radiation.cumulative_dose_equivalent"

# Daily integrals only: cumulative/mean-per-day arithmetic applies to these, not to dose rates.
DAILY_METRICS = (ABSORBED_DOSE_DAILY, DOSE_EQUIVALENT_DAILY)

METRICS = (
    MetricDefinition(
        metric=DOSE_RATE,
        module=ModuleId.RADIATION,
        unit="uGy/h",
        description="Absorbed dose rate from a wearable dosimeter (instantaneous reading).",
        non_negative=True,
        optional_context=("instrument",),
        unit_aliases=("µGy/h", "ugy/h"),
    ),
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
    MetricDefinition(
        metric=DOSE_EQUIVALENT_RATE,
        module=ModuleId.RADIATION,
        unit="uSv/h",
        description="Dose-equivalent rate from a wearable dosimeter (instantaneous reading).",
        non_negative=True,
        optional_context=("instrument",),
        unit_aliases=("µSv/h", "usv/h"),
    ),
    MetricDefinition(
        metric=CUMULATIVE_DOSE_EQUIVALENT,
        module=ModuleId.RADIATION,
        unit="mSv",
        description="Running total of dose equivalent reported by the wearable since mission start.",
        non_negative=True,
        optional_context=("instrument",),
    ),
)
