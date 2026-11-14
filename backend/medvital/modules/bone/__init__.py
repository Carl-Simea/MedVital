from medvital.core.module_spec import HealthModuleSpec
from medvital.core.schema import ModuleId
from medvital.modules.bone.metrics import METRICS
from medvital.modules.bone.service import summarize

SPEC = HealthModuleSpec(
    module_id=ModuleId.BONE,
    name="Bone health",
    description="Areal bone mineral density change and trend per skeletal site.",
    metrics=METRICS,
    summarize=summarize,
    method_notes="docs/SCIENTIFIC_METHODOLOGY.md#3-bone-health",
)

__all__ = ["SPEC"]
