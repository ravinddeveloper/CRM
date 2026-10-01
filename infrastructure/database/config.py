"""Validated persistence engine selection."""
from enum import StrEnum

from decouple import config

from .exceptions import ConfigurationError


class DatabaseEngine(StrEnum):
    SQL = "sql"
    MONGODB = "mongodb"


def get_database_engine(value: str | None = None) -> DatabaseEngine:
    """Read and validate the configured engine without silently falling back."""
    configured = value if value is not None else config("DATABASE_ENGINE", default="sql")
    try:
        return DatabaseEngine(str(configured).strip().lower())
    except ValueError as exc:
        raise ConfigurationError(
            f"Unsupported DATABASE_ENGINE {configured!r}. Supported values are 'sql' and 'mongodb'."
        ) from exc
