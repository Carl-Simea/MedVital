from medvital.core.module_spec import MetricDefinition
from medvital.core.schema import ModuleId

SLEEP_DURATION = "behavioral.sleep_duration"
SELF_REPORT_SCORE = "behavioral.self_report_score"

METRICS = (
    MetricDefinition(
        metric=SLEEP_DURATION,
        module=ModuleId.BEHAVIORAL,
        unit="h",
        description="Sleep duration for one sleep period.",
        non_negative=True,
        optional_context=("device",),
    ),
    MetricDefinition(
        metric=SELF_REPORT_SCORE,
        module=ModuleId.BEHAVIORAL,
        unit="{score}",
        description=(
            "Score from a named self-report instrument. The instrument (and its scale) must be "
            "named in context; scores from different instruments are never pooled."
        ),
        required_context=("instrument",),
    ),
)
