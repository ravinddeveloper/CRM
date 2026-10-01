"""Process-wide PyMongo client with explicit health and shutdown hooks."""
import atexit
from threading import Lock

from decouple import config

from .exceptions import ConfigurationError, DatabaseConnectionError

_client = None
_lock = Lock()


def get_mongo_client():
    """Return the shared MongoClient, creating it only on first use."""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                uri = config("MONGO_URI", default="mongodb://localhost:27017").strip()
                if not uri:
                    raise ConfigurationError("MONGO_URI must be set when DATABASE_ENGINE=mongodb.")
                try:
                    from pymongo import MongoClient
                    _client = MongoClient(uri, serverSelectionTimeoutMS=5000, appname="EduFlow", tz_aware=True)
                    atexit.register(close_mongo_client)
                except ImportError as exc:
                    raise ConfigurationError("MongoDB mode requires the 'pymongo' package.") from exc
    return _client


def get_mongo_database(name: str | None = None):
    """Return a configured database handle; network access remains lazy."""
    database_name = name or config("MONGO_DB_NAME", default="eduflow")
    return get_mongo_client()[database_name]


def check_mongo_connection() -> None:
    """Verify MongoDB connectivity and translate driver errors."""
    try:
        from pymongo.errors import PyMongoError
    except ImportError as exc:
        raise ConfigurationError("MongoDB mode requires the 'pymongo' package.") from exc
    try:
        get_mongo_client().admin.command("ping")
    except PyMongoError as exc:
        raise DatabaseConnectionError("Could not connect to the configured MongoDB server.") from exc


def close_mongo_client() -> None:
    """Close the process-wide client during orderly process shutdown."""
    global _client
    with _lock:
        if _client is not None:
            _client.close()
            _client = None
