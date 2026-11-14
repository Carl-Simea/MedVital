from medvital.core.module_spec import MetricDefinition
from medvital.core.schema import ModuleId

SLEEP_DURATION = "behavioral.sleep_duration"
SELF_REPORT_SCORE = "behavioral.self_report_score"
TIME_IN_BED = "behavioral.time_in_bed"

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
    MetricDefinition(
        metric=TIME_IN_BED,
        module=ModuleId.BEHAVIORAL,
        unit="h",
        description=(
            "Time in bed for one sleep period. Definitions differ between studies (literal in-bed "
            "interval vs intention-to-sleep window), so `tib_definition` is required and values are never "
            "pooled across definitions (Hand & Siengsukon 2025; MODELING_GAP_ANALYSIS G-10)."
        ),
        non_negative=True,
        required_context=("tib_definition",),
        optional_context=("device",),
    ),
)
