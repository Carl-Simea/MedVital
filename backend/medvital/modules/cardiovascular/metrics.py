from medvital.core.module_spec import MetricDefinition
from medvital.core.schema import ModuleId

HEART_RATE = "cardiovascular.heart_rate"
RESTING_HEART_RATE = "cardiovascular.resting_heart_rate"
RR_INTERVAL = "cardiovascular.rr_interval"
SYSTOLIC_BP = "cardiovascular.systolic_bp"
DIASTOLIC_BP = "cardiovascular.diastolic_bp"
STROKE_VOLUME = "cardiovascular.stroke_volume"

METRICS = (
    MetricDefinition(
        metric=HEART_RATE,
        module=ModuleId.CARDIOVASCULAR,
        unit="{beats}/min",
        description="Heart rate from a wearable stream (any activity state).",
        non_negative=True,
        optional_context=("device",),
        unit_aliases=("bpm", "beats/min"),
    ),
    MetricDefinition(
        metric=RESTING_HEART_RATE,
        module=ModuleId.CARDIOVASCULAR,
        unit="{beats}/min",
        description="Resting heart rate.",
        non_negative=True,
        optional_context=("device",),
    ),
    MetricDefinition(
        metric=RR_INTERVAL,
        module=ModuleId.CARDIOVASCULAR,
        unit="ms",
        description="Interval between successive R peaks. Group a recording with context 'session_id'.",
        non_negative=True,
        optional_context=("session_id", "device"),
    ),
    MetricDefinition(
        metric=SYSTOLIC_BP,
        module=ModuleId.CARDIOVASCULAR,
        unit="mm[Hg]",
        description="Systolic blood pressure.",
        non_negative=True,
        optional_context=("device", "posture"),
    ),
    MetricDefinition(
        metric=DIASTOLIC_BP,
        module=ModuleId.CARDIOVASCULAR,
        unit="mm[Hg]",
        description="Diastolic blood pressure.",
        non_negative=True,
        optional_context=("device", "posture"),
    ),
    MetricDefinition(
        metric=STROKE_VOLUME,
        module=ModuleId.CARDIOVASCULAR,
        unit="mL",
        description="Stroke volume per beat from a named assessment method (context `method`).",
        non_negative=True,
        optional_context=("method", "device", "posture"),
    ),
)
