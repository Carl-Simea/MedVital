from uuid import uuid4

import pytest
from pydantic import ValidationError

from medvital.core.provenance import DataOrigin, Provenance


def test_simulated_requires_method_and_seed():
    with pytest.raises(ValidationError):
        Provenance(origin=DataOrigin.SIMULATED, source="s", method="m")
    with pytest.raises(ValidationError):
        Provenance(origin=DataOrigin.SIMULATED, source="s", seed=1)
    Provenance(origin=DataOrigin.SIMULATED, source="s", method="m", seed=1)


def test_simulated_must_not_claim_derivation():
    with pytest.raises(ValidationError):
        Provenance(
            origin=DataOrigin.SIMULATED, source="s", method="m", seed=1, derived_from=(uuid4(),)
        )


def test_measured_requires_source_ref():
    with pytest.raises(ValidationError):
        Provenance(origin=DataOrigin.MEASURED, source="instrument")
    Provenance(origin=DataOrigin.MEASURED, source="instrument", source_ref="dataset-id")


def test_measured_must_not_carry_simulation_fields():
    with pytest.raises(ValidationError):
        Provenance(origin=DataOrigin.MEASURED, source="i", source_ref="r", seed=3)


def test_modeled_requires_method_and_inputs():
    with pytest.raises(ValidationError):
        Provenance(origin=DataOrigin.MODELED, source="m", derived_from=(uuid4(),))
    with pytest.raises(ValidationError):
        Provenance(origin=DataOrigin.MODELED, source="m", method="m")
    Provenance(origin=DataOrigin.MODELED, source="m", method="m", derived_from=(uuid4(),))


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        Provenance(origin=DataOrigin.SIMULATED, source="s", method="m", seed=1, note="x")
