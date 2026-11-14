"""Source import pipeline: turn external tabular data into MEASURED observations.

Depends on ``core`` and ``registry`` only. No NASA data ships here: a source is described by an
``ImportSpec`` that someone fills in after reading that source's terms (docs/NASA_SOURCES.md).
"""

from medvital.importers.csv_import import ImportResult, import_csv, import_frame
from medvital.importers.spec import ColumnSpec, ImportSpec, SpecError, load_spec, validate_spec

__all__ = [
    "ColumnSpec",
    "ImportResult",
    "ImportSpec",
    "SpecError",
    "import_csv",
    "import_frame",
    "load_spec",
    "validate_spec",
]
