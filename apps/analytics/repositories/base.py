"""Backend-neutral analytics records and repository contracts."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CourseViewRecord:
    id: str
    course_id: str
    user_id: str | None
    ip_address: str | None
    session_key: str
    created_at: datetime


class CourseViewRepository(Protocol):
    def record_view(
        self,
        *,
        course_id: str,
        user_id: str | None,
        ip_address: str | None,
        session_key: str,
    ) -> CourseViewRecord: ...

    def get_total_views(self, *, course_id: str) -> int: ...
