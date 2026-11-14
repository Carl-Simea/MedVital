"""Turn a table into validated MEASURED observations according to an ImportSpec."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from medvital.core.observation import HealthObservation
from medvital.core.provenance import DataOrigin, Provenance
from medvital.core.simulation import deterministic_id
from medvital.importers.spec import ImportSpec, validate_spec
from medvital.importers.units import convert
from medvital.registry import MODULES, ObservationRejected, validate_observation


@dataclass(frozen=True)
class Rejection:
    row: int  # zero-based data row index
    column: str | None
    reason: str


@dataclass
class ImportResult:
    observations: list[HealthObservation] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    skipped_empty: int = 0


def _read_table(source: str | Path | io.TextIOBase) -> pd.DataFrame:
    # Everything is read as text so parsing rules (and failures) are ours, not pandas' guesses.
    return pd.read_csv(source, dtype=str, keep_default_na=False)


def import_csv(source: str | Path | io.TextIOBase, spec: ImportSpec) -> ImportResult:
    return import_frame(_read_table(source), spec)


def import_frame(frame: pd.DataFrame, spec: ImportSpec) -> ImportResult:
    """Convert rows to observations. Bad cells are rejected individually; good ones are kept."""
    validate_spec(spec)
    result = ImportResult()
    needed = [spec.time_column, *(c.column for c in spec.columns)]
    if spec.astronaut_id_column:
        needed.append(spec.astronaut_id_column)
    missing = [c for c in needed if c not in frame.columns]
    if missing:
        result.rejections.append(Rejection(-1, None, f"missing columns: {', '.join(missing)}"))
        return result

    seen_ids: set[object] = set()
    for row_index, row in enumerate(frame.to_dict(orient="records")):
        raw_time = str(row[spec.time_column]).strip()
        try:
            stamp = pd.Timestamp(raw_time)
        except (ValueError, TypeError):
            result.rejections.append(Rejection(row_index, spec.time_column, "unparseable time"))
            continue
        if pd.isna(stamp):
            result.rejections.append(Rejection(row_index, spec.time_column, "missing time"))
            continue
        if stamp.tzinfo is None:
            if not spec.assume_utc:
                result.rejections.append(
                    Rejection(row_index, spec.time_column, "time has no timezone")
                )
                continue
            stamp = stamp.tz_localize("UTC")
        observed_at = stamp.to_pydatetime()

        astronaut_id = spec.astronaut_id or str(row[spec.astronaut_id_column or ""]).strip()

        for col in spec.columns:
            text = str(row[col.column]).strip()
            if text == "":
                result.skipped_empty += 1
                continue
            try:
                number = float(text)
            except ValueError:
                result.rejections.append(Rejection(row_index, col.column, "not a number"))
                continue
            if not math.isfinite(number):
                result.rejections.append(Rejection(row_index, col.column, "not a finite number"))
                continue

            metric_spec = MODULES[col.module].spec(col.metric)
            assert metric_spec is not None  # guaranteed by validate_spec
            obs_id = deterministic_id(
                "import", spec.source_ref, astronaut_id, observed_at.isoformat(), col.metric
            )
            if obs_id in seen_ids:
                result.rejections.append(
                    Rejection(row_index, col.column, "duplicate astronaut/time/metric in file")
                )
                continue
            try:
                obs = HealthObservation(
                    id=obs_id,
                    astronaut_id=astronaut_id,
                    module=col.module,
                    metric=col.metric,
                    value=convert(number, col.source_unit, metric_spec.unit),
                    unit=metric_spec.unit,
                    observed_at=observed_at,
                    provenance=Provenance(
                        origin=DataOrigin.MEASURED,
                        source=spec.source,
                        source_ref=spec.source_ref,
                        method=f"import_csv_from_{col.source_unit}"
                        if col.source_unit != metric_spec.unit
                        else "import_csv",
                    ),
                )
                validate_observation(obs)
            except (ValidationError, ObservationRejected) as exc:
                result.rejections.append(Rejection(row_index, col.column, type(exc).__name__))
                continue
            seen_ids.add(obs_id)
            result.observations.append(obs)
    return result
