from medvital.core.module_spec import HealthModuleSpec
from medvital.core.schema import ModuleId
from medvital.modules.cardiovascular.metrics import METRICS
from medvital.modules.cardiovascular.service import summarize

SPEC = HealthModuleSpec(
    module_id=ModuleId.CARDIOVASCULAR,
    name="Cardiovascular health",
    description="Resting heart rate, blood pressure and RR-interval heart-rate-variability (RMSSD).",
    metrics=METRICS,
    summarize=summarize,
    method_notes="docs/SCIENTIFIC_METHODOLOGY.md#4-cardiovascular-health",
)

__all__ = ["SPEC"]
