"""PostgreSQL architecture checks that need no live database.

The PostgreSQL repository itself is NOT exercised here (see docs/DECISIONS.md).
"""

from medvital.config import Settings
from medvital.core.observation import ModuleId
from medvital.core.provenance import DataOrigin
from medvital.db.factory import make_repository
from medvital.db.postgres import SCHEMA_PATH
from medvital.db.repository import InMemoryObservationRepository


def test_factory_defaults_to_in_memory_without_database_url():
    assert isinstance(make_repository(Settings()), InMemoryObservationRepository)


def test_settings_read_database_url_from_environment(monkeypatch):
    monkeypatch.setenv("MEDVITAL_DATABASE_URL", "postgresql://example/db")
    assert Settings.from_env().database_url == "postgresql://example/db"
    monkeypatch.setenv("MEDVITAL_DATABASE_URL", "")
    assert Settings.from_env().database_url is None


def test_schema_sql_checks_match_python_enums():
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    for module in ModuleId:
        assert f"'{module.value}'" in sql
    for origin in DataOrigin:
        assert f"'{origin.value}'" in sql
    assert "server_seq" in sql and "PRIMARY KEY" in sql
