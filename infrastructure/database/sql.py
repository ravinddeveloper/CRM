"""SQL connection URL construction shared by Django settings and tests."""
from urllib.parse import quote


def build_sql_database_url(
    *,
    database_url: str = "",
    db_host: str = "",
    db_port: int | str = 5432,
    db_name: str = "myportal",
    db_user: str = "",
    db_password: str = "",
    sqlite_url: str,
) -> str:
    """Prefer DATABASE_URL, then PostgreSQL DB_* values, then local SQLite."""
    configured_url = database_url.strip()
    if configured_url:
        return configured_url
    if db_host.strip():
        user = quote(db_user, safe="")
        password = quote(db_password, safe="")
        credentials = f"{user}:{password}@" if user or password else ""
        return f"postgresql://{credentials}{db_host.strip()}:{db_port}/{db_name}"
    return sqlite_url
