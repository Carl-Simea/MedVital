"""Enforces the module-independence and science/presentation separation rules via imports."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1] / "medvital"
MODULE_NAMES = ["radiation", "bone", "cardiovascular", "behavioral"]


def imported_modules(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def violations(files: list[Path], forbidden_prefixes: list[str]) -> list[str]:
    found = []
    for f in files:
        for name in imported_modules(f):
            if any(name == p or name.startswith(p + ".") for p in forbidden_prefixes):
                found.append(f"{f.relative_to(PKG)} imports {name}")
    return found


@pytest.mark.parametrize("module", MODULE_NAMES)
def test_health_module_depends_only_on_itself_and_core(module):
    others = [f"medvital.modules.{m}" for m in MODULE_NAMES if m != module]
    forbidden = [
        *others,
        "fastapi",
        "starlette",
        "medvital.api",
        "medvital.db",
        "medvital.sync",
        "medvital.registry",
        "medvital.ingest",
        "medvital.main",
        "medvital.simulated_profiles",
    ]
    files = list((PKG / "modules" / module).rglob("*.py"))
    assert files, f"no files found for module {module}"
    assert violations(files, forbidden) == []


def test_calculations_files_are_pure_numerics():
    """calculations.py must not know about observations, provenance, HTTP or storage."""
    forbidden = [
        "fastapi",
        "pydantic",
        "medvital.api",
        "medvital.db",
        "medvital.sync",
        "medvital.registry",
        "medvital.core.observation",
        "medvital.core.provenance",
        "medvital.core.module",
    ]
    files = list((PKG / "modules").rglob("calculations.py"))
    assert len(files) == len(MODULE_NAMES)
    assert violations(files, forbidden) == []


def test_core_does_not_depend_on_framework_or_upper_layers():
    forbidden = [
        "fastapi",
        "starlette",
        "medvital.api",
        "medvital.db",
        "medvital.sync",
        "medvital.modules",
        "medvital.registry",
        "medvital.ingest",
    ]
    assert violations(list((PKG / "core").rglob("*.py")), forbidden) == []


def test_database_layer_does_not_import_api_or_modules():
    forbidden = ["fastapi", "medvital.api", "medvital.modules", "medvital.registry"]
    assert violations(list((PKG / "db").rglob("*.py")), forbidden) == []
