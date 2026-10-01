import pytest

from infrastructure.database.config import DatabaseEngine, get_database_engine
from infrastructure.database.exceptions import ConfigurationError
from infrastructure.database.sql import build_sql_database_url


@pytest.mark.parametrize(
    ("value", "expected"),
    [("sql", DatabaseEngine.SQL), ("mongodb", DatabaseEngine.MONGODB), (" MongoDB ", DatabaseEngine.MONGODB)],
)
def test_database_engine_is_normalized(value, expected):
    assert get_database_engine(value) is expected


def test_unsupported_database_engine_fails_clearly():
    with pytest.raises(ConfigurationError, match="Supported values are 'sql' and 'mongodb'"):
        get_database_engine("mysql")


def test_django_startup_validates_the_database_engine(monkeypatch):
    from importlib import import_module

    from apps.common.apps import CommonConfig

    monkeypatch.setenv("DATABASE_ENGINE", "mysql")
    with pytest.raises(ConfigurationError, match="Unsupported DATABASE_ENGINE 'mysql'"):
        CommonConfig("common", import_module("apps.common")).ready()


def test_sql_database_url_takes_precedence_over_components():
    assert build_sql_database_url(
        database_url="postgresql://db.example/portal",
        db_host="ignored.example",
        sqlite_url="sqlite:///db.sqlite3",
    ) == "postgresql://db.example/portal"


def test_postgres_database_components_escape_credentials():
    assert build_sql_database_url(
        db_host="postgres.internal",
        db_port=5433,
        db_name="portal",
        db_user="portal user",
        db_password="P@ss:word",
        sqlite_url="sqlite:///db.sqlite3",
    ) == "postgresql://portal%20user:P%40ss%3Aword@postgres.internal:5433/portal"


def test_sqlite_is_the_local_fallback():
    assert build_sql_database_url(sqlite_url="sqlite:///db.sqlite3") == "sqlite:///db.sqlite3"
