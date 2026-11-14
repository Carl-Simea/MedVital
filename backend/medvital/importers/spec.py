"""Import specification: how one external table maps onto MEDVITAL metrics."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from medvital.core.observation import ASTRONAUT_ID_PATTERN, METRIC_PATTERN, ModuleId
from medvital.core.provenance import DataOrigin
from medvital.importers.units import can_convert
from medvital.registry import MODULES


class SpecError(ValueError):
    """The import spec is invalid for MEDVITAL's registry or unit table."""


class ColumnSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    column: str = Field(min_length=1)
    module: ModuleId
    metric: str = Field(pattern=METRIC_PATTERN)
    # Unit as stated by the source. Converted to the metric's unit by an exact conversion.
    source_unit: str = Field(min_length=1, max_length=32)


class ImportSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # Producer, e.g. an instrument or archive name. Never empty.
    source: str = Field(min_length=1, max_length=200)
    # Citation, dataset id or URL identifying exactly what was imported (provenance.source_ref).
    source_ref: str = Field(min_length=1, max_length=500)
    # What the source's terms of use say about reuse, in the importer's own words. Required so
    # nobody imports data without having read the terms.
    terms_note: str = Field(min_length=10, max_length=1000)
    # Exactly one of these identifies the person the rows belong to.
    astronaut_id_column: str | None = None
    astronaut_id: str | None = Field(default=None, pattern=ASTRONAUT_ID_PATTERN)
    time_column: str = Field(min_length=1)
    # Naive timestamps are rejected unless the importer asserts the source is UTC.
    assume_utc: bool = False
    columns: tuple[ColumnSpec, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_identity(self) -> ImportSpec:
        if (self.astronaut_id_column is None) == (self.astronaut_id is None):
            raise ValueError("set exactly one of 'astronaut_id_column' and 'astronaut_id'")
        return self


def validate_spec(spec: ImportSpec) -> None:
    """Check every column against the module registry and unit table."""
    seen: set[tuple[str, str]] = set()
    for col in spec.columns:
        module = MODULES.get(col.module)
        metric = module.spec(col.metric) if module else None
        if metric is None:
            raise SpecError(f"metric '{col.metric}' is not defined for module '{col.module}'")
        if DataOrigin.MEASURED not in metric.allowed_origins:
            raise SpecError(f"metric '{col.metric}' cannot hold measured data")
        if not can_convert(col.source_unit, metric.unit):
            raise SpecError(
                f"no exact conversion from '{col.source_unit}' to '{metric.unit}' "
                f"for metric '{col.metric}'"
            )
        key = (col.column, col.metric)
        if key in seen:
            raise SpecError(f"duplicate mapping for column '{col.column}' and '{col.metric}'")
        seen.add(key)


def load_spec(path: str | Path) -> ImportSpec:
    spec = ImportSpec.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
    validate_spec(spec)
    return spec
