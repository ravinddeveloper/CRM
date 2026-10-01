"""Backend-neutral enrollment records and repository contract."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class EnrollmentRecord:
    id: str
    user_id: str
    course_id: str
    status: str
    access_type: str
    expires_at: datetime | None
    created_at: datetime


class EnrollmentRepository(Protocol):
    def list_for_user(self, *, user_id: str, limit: int, offset: int) -> tuple[int, list[EnrollmentRecord]]: ...
