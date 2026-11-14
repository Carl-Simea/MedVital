"""Regenerate the shared contract files in ../contracts.

Run from the backend directory:  python scripts/export_contracts.py
tests/test_contracts.py fails if the committed files are out of date.
"""

from __future__ import annotations

import json
from pathlib import Path

from medvital.core.observation import HealthObservation

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"


def build_schema() -> dict:
    return HealthObservation.model_json_schema()


def render(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def main() -> None:
    CONTRACTS_DIR.mkdir(exist_ok=True)
    (CONTRACTS_DIR / "observation.schema.json").write_text(render(build_schema()), encoding="utf-8")
    print(f"wrote {CONTRACTS_DIR / 'observation.schema.json'}")


if __name__ == "__main__":
    main()
