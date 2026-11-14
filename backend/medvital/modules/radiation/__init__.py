from medvital.core.module_spec import HealthModuleSpec
from medvital.core.schema import ModuleId
from medvital.modules.radiation.metrics import METRICS
from medvital.modules.radiation.service import summarize

SPEC = HealthModuleSpec(
    module_id=ModuleId.RADIATION,
    name="Radiation",
    description="Accumulated absorbed dose and dose equivalent from daily dosimetry observations.",
    metrics=METRICS,
    summarize=summarize,
    method_notes="docs/SCIENTIFIC_METHODOLOGY.md#2-radiation",
)

__all__ = ["SPEC"]
