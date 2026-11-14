from medvital.core.module_spec import HealthModuleSpec
from medvital.core.schema import ModuleId
from medvital.modules.behavioral.metrics import METRICS
from medvital.modules.behavioral.service import summarize

SPEC = HealthModuleSpec(
    module_id=ModuleId.BEHAVIORAL,
    name="Behavioral health",
    description="Sleep and self-report series expressed relative to each subject's own baseline.",
    metrics=METRICS,
    summarize=summarize,
    method_notes="docs/SCIENTIFIC_METHODOLOGY.md#5-behavioral-health",
)

__all__ = ["SPEC"]
