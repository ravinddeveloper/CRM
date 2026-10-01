"""Backend-neutral audit log contract."""
from typing import Protocol


class AuditLogRepository(Protocol):
    def create(self, **values) -> dict: ...

    def list_recent(self, *, action: str | None = None, limit: int = 150) -> list[dict]: ...
