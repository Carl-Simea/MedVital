"""Write the OpenAPI contract to docs/api/openapi.json.

    python backend/scripts/export_openapi.py          # write
    python backend/scripts/export_openapi.py --check  # exit 1 if the committed file is stale
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from medvital.config import Settings
from medvital.main import create_app

TARGET = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json"


def render() -> str:
    app = create_app(Settings(repository="memory"))
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    text = render()
    if "--check" in sys.argv:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != text:
            print(f"{TARGET} is out of date; run backend/scripts/export_openapi.py", file=sys.stderr)
            raise SystemExit(1)
        print("openapi.json is up to date")
    else:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {TARGET}")
