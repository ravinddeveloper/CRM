"""Backend-neutral published course catalog contract."""
from typing import Protocol


class CourseCatalogRepository(Protocol):
    def list_published(self, *, category: str | None, search: str, difficulty: str | None,
                       is_free: bool | None, limit: int, offset: int) -> tuple[int, list[dict]]: ...
