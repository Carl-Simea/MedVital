"""Reusable, cross-domain analysis engine (descriptive stats, personal baselines, data
quality, statistical anomaly flags). Imports only ``medvital.core``; health modules never
import it. See docs/SCIENTIFIC_METHODOLOGY.md §9 and docs/DECISIONS.md D-018.
"""

from medvital.analysis.engine import analyze
from medvital.analysis.models import (
    ANALYSIS_NOTICE,
    ANALYSIS_VERSION,
    AnalysisConfig,
    AnalysisReport,
    BaselineSpec,
)

__all__ = [
    "ANALYSIS_NOTICE",
    "ANALYSIS_VERSION",
    "AnalysisConfig",
    "AnalysisReport",
    "BaselineSpec",
    "analyze",
]
