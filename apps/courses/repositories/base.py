"""Backend-neutral published course catalog contract."""
from typing import Protocol


class CourseCatalogRepository(Protocol):
    def list_published(self, *, category: str | None, search: str, difficulty: str | None,
                       is_free: bool | None, price_min: str | None = None, price_max: str | None = None,
                       sort: str = "newest", featured_only: bool = False,
                       include_related_search: bool = False,
                       limit: int = 20, offset: int = 0) -> tuple[int, list[dict]]: ...

    def get_by_id(self, course_id: str) -> dict | None: ...

    def get_by_slug(self, slug: str) -> dict | None: ...

    def list_categories(self, *, root_only: bool = False) -> list[dict]: ...

    def get_category_by_slug(self, slug: str) -> dict | None: ...
