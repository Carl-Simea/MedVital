"""Dependency rules for medvital.analysis (kept separate from test_architecture.py)."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "medvital"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                found.add("<relative>")
            elif node.module:
                found.add(node.module)
    return found


def test_analysis_calculations_are_pure():
    forbidden = (
        "medvital",
        "fastapi",
        "pydantic",
        "requests",
        "httpx",
        "os",
        "pathlib",
        "sqlite3",
        "<relative>",
    )
    for name in _imports(ROOT / "analysis" / "calculations.py"):
        assert name.split(".")[0] not in forbidden, f"analysis/calculations.py imports {name}"


def test_analysis_depends_only_on_core_and_itself():
    for path in (ROOT / "analysis").rglob("*.py"):
        for name in _imports(path):
            if name == "medvital" or name.startswith("medvital."):
                assert name.startswith(("medvital.core", "medvital.analysis")), f"{path.name} imports {name}"


def test_nothing_below_api_imports_analysis():
    for sub in ("core", "modules", "simulation", "db"):
        for path in (ROOT / sub).rglob("*.py"):
            assert not any(n.startswith("medvital.analysis") for n in _imports(path)), path
