"""Import pipeline tests.

ALL DATA HERE IS SYNTHETIC TEST FIXTURE DATA. It is not NASA data and imitates no real dataset.
"""

import io
import json

import pytest
from pydantic import ValidationError

from medvital.core.observation import ModuleId
from medvital.core.provenance import DataOrigin
from medvital.db.repository import InMemoryObservationRepository
from medvital.importers import (
    ColumnSpec,
    ImportSpec,
    SpecError,
    import_csv,
    load_spec,
    validate_spec,
)
from medvital.importers.units import can_convert, convert
from medvital.ingest import ingest

TERMS = "Synthetic test fixture; no real terms apply."


def spec(**overrides) -> ImportSpec:
    base = dict(
        source="test-fixture",
        source_ref="fixture://radiation-v1",
        terms_note=TERMS,
        astronaut_id="FIX-001",
        time_column="time",
        columns=(
            ColumnSpec(
                column="dose",
                module=ModuleId.RADIATION,
                metric="absorbed_dose_rate",
                source_unit="mGy/day",
            ),
        ),
    )
    base.update(overrides)
    return ImportSpec(**base)


def csv(text: str) -> io.StringIO:
    return io.StringIO(text)


# --- units ---------------------------------------------------------------------------------


def test_unit_conversions_match_hand_computed_values():
    assert convert(0.25, "mGy/day", "uGy/day") == pytest.approx(250.0)
    assert convert(90.0, "min", "h") == pytest.approx(1.5)
    assert convert(1.5, "s", "ms") == pytest.approx(1500.0)
    # 16 kPa = 16000 Pa; 1 mmHg = 133.322387415 Pa -> 16000 / 133.322387415 = 120.00986
    assert convert(16.0, "kPa", "mmHg") == pytest.approx(120.00986, abs=1e-4)
    assert convert(5.0, "bpm", "bpm") == 5.0


def test_unknown_conversion_is_refused():
    assert not can_convert("mmHg", "kPa")  # only listed directions exist
    with pytest.raises(ValueError):
        convert(1.0, "furlong", "uGy/day")


# --- importing -----------------------------------------------------------------------------


def test_imports_measured_observations_with_converted_units_and_provenance():
    data = "time,dose\n2030-01-01T00:00:00Z,0.25\n2030-01-02T00:00:00Z,0.5\n"
    result = import_csv(csv(data), spec())
    assert result.rejections == []
    assert [o.value for o in result.observations] == pytest.approx([250.0, 500.0])
    first = result.observations[0]
    assert first.unit == "uGy/day"
    assert first.astronaut_id == "FIX-001"
    assert first.provenance.origin is DataOrigin.MEASURED
    assert first.provenance.source_ref == "fixture://radiation-v1"
    assert first.provenance.method == "import_csv_from_mGy/day"


def test_astronaut_id_can_come_from_a_column():
    data = "time,who,dose\n2030-01-01T00:00:00Z,FIX-A,1\n2030-01-01T00:00:00Z,FIX-B,2\n"
    s = spec(astronaut_id=None, astronaut_id_column="who")
    result = import_csv(csv(data), s)
    assert {o.astronaut_id for o in result.observations} == {"FIX-A", "FIX-B"}


def test_naive_times_rejected_unless_utc_is_asserted():
    data = "time,dose\n2030-01-01 12:00:00,1\n"
    strict = import_csv(csv(data), spec())
    assert strict.observations == []
    assert strict.rejections[0].reason == "time has no timezone"

    lenient = import_csv(csv(data), spec(assume_utc=True))
    assert len(lenient.observations) == 1
    assert lenient.observations[0].observed_at.hour == 12


def test_bad_cells_are_rejected_individually_and_empty_cells_skipped():
    data = (
        "time,dose\n"
        "2030-01-01T00:00:00Z,1\n"
        "2030-01-02T00:00:00Z,abc\n"
        "2030-01-03T00:00:00Z,\n"
        "2030-01-04T00:00:00Z,nan\n"
        "not-a-time,5\n"
        "2030-01-06T00:00:00Z,-3\n"
        "2030-01-07T00:00:00Z,2\n"
    )
    result = import_csv(csv(data), spec())
    assert len(result.observations) == 3  # rows 0, 5 (negative is valid at schema level), 6
    assert result.skipped_empty == 1
    reasons = {(r.row, r.reason) for r in result.rejections}
    assert (1, "not a number") in reasons
    assert (3, "not a finite number") in reasons
    assert (4, "unparseable time") in reasons


def test_missing_columns_reported_without_crashing():
    result = import_csv(csv("time,other\n2030-01-01T00:00:00Z,1\n"), spec())
    assert result.observations == []
    assert "missing columns: dose" in result.rejections[0].reason


def test_duplicate_rows_in_one_file_are_rejected():
    data = "time,dose\n2030-01-01T00:00:00Z,1\n2030-01-01T00:00:00Z,2\n"
    result = import_csv(csv(data), spec())
    assert len(result.observations) == 1
    assert result.rejections[0].reason.startswith("duplicate")


def test_ids_are_stable_across_reorderings_so_reimport_is_idempotent():
    a = "time,dose\n2030-01-01T00:00:00Z,1\n2030-01-02T00:00:00Z,2\n"
    b = "time,dose\n2030-01-02T00:00:00Z,2\n2030-01-01T00:00:00Z,1\n"
    ids_a = {o.id for o in import_csv(csv(a), spec()).observations}
    ids_b = {o.id for o in import_csv(csv(b), spec()).observations}
    assert ids_a == ids_b


def test_different_source_ref_gives_different_ids():
    data = "time,dose\n2030-01-01T00:00:00Z,1\n"
    one = import_csv(csv(data), spec()).observations[0].id
    two = import_csv(csv(data), spec(source_ref="fixture://other")).observations[0].id
    assert one != two


def test_imported_observations_pass_the_normal_ingest_path():
    data = "time,dose\n2030-01-01T00:00:00Z,1\n2030-01-02T00:00:00Z,2\n"
    result = import_csv(csv(data), spec())
    repo = InMemoryObservationRepository()
    payload = [o.model_dump(mode="json") for o in result.observations]
    first = ingest(repo, payload)
    assert len(first.accepted) == 2 and first.rejected == []
    assert len(ingest(repo, payload).duplicates) == 2


# --- spec validation -----------------------------------------------------------------------


def test_spec_requires_exactly_one_identity_source():
    with pytest.raises(ValidationError):
        spec(astronaut_id=None)
    with pytest.raises(ValidationError):
        spec(astronaut_id_column="who")


def test_spec_requires_terms_note_and_columns():
    with pytest.raises(ValidationError):
        spec(terms_note="")
    with pytest.raises(ValidationError):
        spec(columns=())


def col(metric: str, unit: str, module=ModuleId.RADIATION) -> ColumnSpec:
    return ColumnSpec(column="c", module=module, metric=metric, source_unit=unit)


def test_validate_spec_rejects_unknown_derived_and_unconvertible_metrics():
    with pytest.raises(SpecError, match="not defined"):
        validate_spec(spec(columns=(col("made_up", "uGy/day"),)))
    with pytest.raises(SpecError, match="cannot hold measured"):
        validate_spec(spec(columns=(col("cumulative_absorbed_dose", "uGy"),)))
    with pytest.raises(SpecError, match="no exact conversion"):
        validate_spec(spec(columns=(col("absorbed_dose_rate", "rad/day"),)))


def test_load_spec_reads_and_validates_json(tmp_path):
    path = tmp_path / "spec.json"
    path.write_text(
        json.dumps(
            {
                "source": "test-fixture",
                "source_ref": "fixture://x",
                "terms_note": TERMS,
                "astronaut_id": "FIX-001",
                "time_column": "time",
                "columns": [
                    {
                        "column": "dose",
                        "module": "radiation",
                        "metric": "absorbed_dose_rate",
                        "source_unit": "uGy/day",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert load_spec(path).columns[0].metric == "absorbed_dose_rate"

    path.write_text(path.read_text().replace("absorbed_dose_rate", "nope"), encoding="utf-8")
    with pytest.raises(SpecError):
        load_spec(path)
