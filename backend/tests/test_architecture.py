"""Enforce module independence and the calculation/presentation split."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "medvital"
MODULES = ["radiation", "bone", "cardiovascular", "behavioral"]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


@pytest.mark.parametrize("module", MODULES)
def test_module_depends_only_on_core(module):
    allowed_prefixes = ("medvital.core", f"medvital.modules.{module}")
    for path in (ROOT / "modules" / module).rglob("*.py"):
        for name in _imports(path):
            if name == "medvital" or name.startswith("medvital."):
                assert name.startswith(allowed_prefixes), f"{path.name} imports {name}"


@pytest.mark.parametrize("module", MODULES)
def test_calculations_are_pure(module):
    """calculations.py may use numpy/scipy/pandas/sklearn only — no medvital, web or I/O."""
    path = ROOT / "modules" / module / "calculations.py"
    forbidden = ("medvital", "fastapi", "pydantic", "requests", "httpx", "os", "pathlib", "sqlite3")
    for name in _imports(path):
        top = name.split(".")[0]
        assert top not in forbidden, f"{module}/calculations.py imports {name}"


def test_device_package_depends_only_on_core_and_stdlib():
    """Devices run on small machines (e.g. a Raspberry Pi): no web framework, DB, or module imports."""
    for path in (ROOT / "device").rglob("*.py"):
        for name in _imports(path):
            if name == "medvital" or name.startswith("medvital."):
                assert name.startswith(("medvital.core", "medvital.device")), f"{path.name} imports {name}"
            assert name.split(".")[0] not in {"fastapi", "pydantic", "pandas", "scipy", "sklearn", "sqlite3"}, (
                f"{path.name} imports {name}"
            )


def test_core_does_not_import_modules_or_api():
    for path in (ROOT / "core").rglob("*.py"):
        for name in _imports(path):
            assert not name.startswith(("medvital.modules", "medvital.api", "medvital.db")), (
                f"core/{path.name} imports {name}"
            )
