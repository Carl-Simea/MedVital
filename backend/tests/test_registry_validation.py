import pytest

from conftest import make_obs
from medvital.core.module_spec import ObservationRejected
from medvital.core.schema import ModuleId
from medvital.registry import build_registry


@pytest.fixture(scope="module")
def registry():
    return build_registry()


def test_all_four_modules_registered(registry):
    assert [m.module_id for m in registry.modules()] == [
        ModuleId.BEHAVIORAL,
        ModuleId.BONE,
        ModuleId.CARDIOVASCULAR,
        ModuleId.RADIATION,
    ]


def test_accepts_valid(registry):
    registry.validate(make_obs())


def test_rejects_unknown_metric(registry):
    with pytest.raises(ObservationRejected, match="unknown metric"):
        registry.validate(make_obs("radiation.made_up", unit="mGy", module=ModuleId.RADIATION))


def test_rejects_wrong_unit(registry):
    with pytest.raises(ObservationRejected, match="canonical unit"):
        registry.validate(make_obs(unit="rad"))


def test_rejects_negative_dose(registry):
    with pytest.raises(ObservationRejected, match="negative"):
        registry.validate(make_obs(value=-0.1))


def test_requires_instrument_for_self_report(registry):
    with pytest.raises(ObservationRejected, match="requires context"):
        registry.validate(make_obs("behavioral.self_report_score", 3.0))
    registry.validate(make_obs("behavioral.self_report_score", 3.0, context={"instrument": "X"}))


def test_rejects_undeclared_context_key(registry):
    with pytest.raises(ObservationRejected, match="does not accept context"):
        registry.validate(make_obs(context={"colour": "red"}))


def test_no_clinical_thresholds_in_definitions(registry):
    """Metric definitions may only carry physical-plausibility flags, never clinical limits."""
    from dataclasses import fields

    from medvital.core.module_spec import MetricDefinition

    assert {f.name for f in fields(MetricDefinition)} == {
        "metric", "module", "unit", "description", "non_negative", "required_context", "optional_context",
    }
