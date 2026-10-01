"""Durably enqueue committed enrollment changes for the Mongo read model."""
import logging

from decouple import config
from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from infrastructure.database.config import DatabaseEngine, get_database_engine

from .models import Enrollment, EnrollmentSyncEvent

logger = logging.getLogger("apps.enrollments")


def _snapshot(enrollment):
    return {
        "public_id": str(enrollment.pk),
        "user_id": str(enrollment.user_id),
        "course_id": str(enrollment.course_id),
        "status": enrollment.status,
        "access_type": enrollment.access_type,
        "expires_at": enrollment.expires_at.isoformat() if enrollment.expires_at else None,
        "created_at": enrollment.created_at.isoformat(),
    }


def _schedule_sync(event_id):
    try:
        from .tasks import process_enrollment_sync_event

        process_enrollment_sync_event.delay(event_id)
    except Exception:
        # The SQL outbox row remains durable and can be drained by the retry command.
        logger.exception("Could not dispatch enrollment sync event %s; it remains queued.", event_id)


def _enqueue(event_type, enrollment):
    projection_enabled = config("MONGO_ENROLLMENT_SYNC_ENABLED", default=False, cast=bool)
    if get_database_engine() is not DatabaseEngine.MONGODB and not projection_enabled:
        return
    event = EnrollmentSyncEvent.objects.create(
        event_type=event_type,
        enrollment_id=enrollment.pk,
        payload=_snapshot(enrollment) if event_type == EnrollmentSyncEvent.UPSERT else {},
    )
    transaction.on_commit(lambda: _schedule_sync(event.pk))


@receiver(post_save, sender=Enrollment, dispatch_uid="enrollments.mongo_outbox.save")
def enrollment_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        _enqueue(EnrollmentSyncEvent.UPSERT, instance)


@receiver(pre_delete, sender=Enrollment, dispatch_uid="enrollments.mongo_outbox.delete")
def enrollment_deleted(sender, instance, **kwargs):
    _enqueue(EnrollmentSyncEvent.DELETE, instance)
