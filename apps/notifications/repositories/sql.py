"""SQL adapter for in-app notifications."""
from django.db import DatabaseError

from apps.notifications.models import Notification
from infrastructure.database.exceptions import DatabaseConnectionError, EntityNotFoundError

from .base import NotificationRecord


class SQLNotificationRepository:
    """Uses Django ORM while returning backend-neutral notification records."""

    @staticmethod
    def _record(notification):
        return NotificationRecord(
            id=str(notification.id), user_id=str(notification.user_id),
            notification_type=notification.notification_type, title=notification.title,
            message=notification.message, action_url=notification.action_url, is_read=notification.is_read,
            read_at=notification.read_at, created_at=notification.created_at,
        )

    def create(self, *, user_id, notification_type, title, message, action_url):
        try:
            notification = Notification.objects.create(
                user_id=user_id,
                notification_type=notification_type,
                title=title,
                message=message,
                action_url=action_url,
            )
            return self._record(notification)
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not create the notification.") from exc

    def list_for_user(self, *, user_id, limit, offset):
        try:
            notifications = Notification.objects.filter(user_id=user_id).order_by("-created_at", "-id")
            count = notifications.count()
            records = [self._record(item) for item in notifications[offset:offset + limit]]
            return count, records
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not list notifications.") from exc

    def mark_read(self, *, notification_id, user_id):
        from django.utils import timezone

        try:
            notification = Notification.objects.filter(pk=notification_id, user_id=user_id).first()
            if notification is None:
                raise EntityNotFoundError("Notification was not found.")
            if not notification.is_read:
                notification.is_read = True
                notification.read_at = timezone.now()
                notification.save(update_fields=["is_read", "read_at"])
            return self._record(notification)
        except (ValueError, TypeError) as exc:
            raise EntityNotFoundError("Notification was not found.") from exc
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not update the notification.") from exc
