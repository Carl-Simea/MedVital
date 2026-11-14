import subprocess
import sys
from pathlib import Path

import pytest

from medvital.config import Settings
from medvital.db.factory import build_repository

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_openapi.py"


def test_committed_openapi_matches_code():
    """docs/api/openapi.json is the API contract; regenerate it when routes change."""
    result = subprocess.run([sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_postgres_requires_url():
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        build_repository(Settings(repository="postgres"))


def test_postgres_is_explicitly_not_implemented():
    with pytest.raises(NotImplementedError):
        build_repository(Settings(repository="postgres", database_url="postgresql://x"))


def test_unknown_repository():
    with pytest.raises(RuntimeError):
        build_repository(Settings(repository="mongo"))


def test_schema_sql_ships_with_package():
    from importlib.resources import files

    sql = (files("medvital.db") / "schema.sql").read_text(encoding="utf-8")
    assert "append-only" in sql and "data_origin" in sql


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("MEDVITAL_CORS_ORIGINS", "http://a.test, http://b.test")
    monkeypatch.setenv("MEDVITAL_REPOSITORY", "MEMORY")
    s = Settings.from_env()
    assert s.cors_origins == ("http://a.test", "http://b.test") and s.repository == "memory"
