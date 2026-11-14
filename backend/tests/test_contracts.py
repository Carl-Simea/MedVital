import json
import sys
from pathlib import Path

from medvital.core.observation import HealthObservation

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "scripts"))

import export_contracts  # noqa: E402


def test_committed_schema_matches_pydantic_model():
    committed = (ROOT / "contracts" / "observation.schema.json").read_text(encoding="utf-8")
    assert committed == export_contracts.render(export_contracts.build_schema()), (
        "contracts/observation.schema.json is stale; run: python scripts/export_contracts.py"
    )


def test_example_observation_is_valid_against_the_model():
    raw = json.loads((ROOT / "contracts" / "observation.example.json").read_text(encoding="utf-8"))
    obs = HealthObservation.model_validate(raw)
    assert obs.provenance.origin.value == "simulated"
