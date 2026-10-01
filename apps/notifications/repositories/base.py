"""Backend-neutral notification records and repository contract."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class NotificationRecord:
    id: str
    user_id: str
    notification_type: str
    title: str
    message: str
    action_url: str
    is_read: bool
    read_at: datetime | None
    created_at: datetime


class NotificationRepository(Protocol):
    def create(self, *, user_id: str, notification_type: str, title: str, message: str, action_url: str) -> NotificationRecord: ...
    def list_for_user(self, *, user_id: str, limit: int, offset: int) -> tuple[int, list[NotificationRecord]]: ...
    def mark_read(self, *, notification_id: str, user_id: str) -> NotificationRecord: ...
