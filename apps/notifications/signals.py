"""Capture SQL notification changes for a safe Mongo cutover."""
import logging

from decouple import config
from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from infrastructure.database.config import DatabaseEngine, get_database_engine

from .models import Notification, NotificationSyncEvent

logger = logging.getLogger("apps.notifications")


def _schedule_sync(event_id):
    try:
        from .tasks import process_notification_sync_event

        process_notification_sync_event.delay(event_id)
    except Exception:
        logger.exception("Could not dispatch notification sync event %s; it remains queued.", event_id)


def _enqueue(event_type, notification):
    projection_enabled = config("MONGO_NOTIFICATION_SYNC_ENABLED", default=False, cast=bool)
    if get_database_engine() is not DatabaseEngine.MONGODB and not projection_enabled:
        return
    event = NotificationSyncEvent.objects.create(
        event_type=event_type,
        notification_id=notification.pk,
    )
    transaction.on_commit(lambda: _schedule_sync(event.pk))


@receiver(post_save, sender=Notification, dispatch_uid="notifications.mongo_outbox.save")
def notification_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        _enqueue(NotificationSyncEvent.UPSERT, instance)


@receiver(pre_delete, sender=Notification, dispatch_uid="notifications.mongo_outbox.delete")
def notification_deleted(sender, instance, **kwargs):
    _enqueue(NotificationSyncEvent.DELETE, instance)
