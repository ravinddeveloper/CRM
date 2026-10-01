"""Retryable tasks for the SQL-to-Mongo enrollment read model."""
import logging

from celery import shared_task
from decouple import config
from infrastructure.database.config import DatabaseEngine, get_database_engine
from django.utils import timezone

from apps.enrollments.models import Enrollment, EnrollmentSyncEvent
from apps.enrollments.repositories.mongo import MongoEnrollmentRepository

logger = logging.getLogger("apps.enrollments")


def process_event(event_id):
    event = EnrollmentSyncEvent.objects.filter(pk=event_id, processed_at__isnull=True).first()
    if event is None:
        return False
    try:
        repository = MongoEnrollmentRepository()
        if event.event_type == EnrollmentSyncEvent.DELETE:
            repository.delete_by_id(event.enrollment_id, source_revision=event.pk)
        else:
            enrollment = Enrollment.objects.filter(pk=event.enrollment_id).first()
            if enrollment is None:
                # A queued save can outlive a later delete; never resurrect stale data.
                repository.delete_by_id(event.enrollment_id, source_revision=event.pk)
            else:
                repository.sync_sql_record(enrollment, source_revision=event.pk)
        event.processed_at = timezone.now()
        event.last_error = ""
        event.save(update_fields=["processed_at", "last_error"])
        return True
    except Exception as exc:
        event.attempts += 1
        event.last_error = str(exc)[:4000]
        event.save(update_fields=["attempts", "last_error"])
        raise


@shared_task(bind=True, max_retries=8, default_retry_delay=30)
def process_enrollment_sync_event(self, event_id):
    try:
        process_event(event_id)
    except EnrollmentSyncEvent.DoesNotExist:
        logger.info("Enrollment sync event %s was already removed or processed.", event_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=min(30 * (2 ** self.request.retries), 1800))


@shared_task(ignore_result=True)
def drain_pending_enrollment_sync_events(batch_size=200):
    """Recover outbox rows whose on-commit dispatch was lost during an outage."""
    sync_enabled = config("MONGO_ENROLLMENT_SYNC_ENABLED", default=False, cast=bool)
    if get_database_engine() is not DatabaseEngine.MONGODB and not sync_enabled:
        return 0

    event_ids = EnrollmentSyncEvent.objects.filter(
        processed_at__isnull=True
    ).order_by("created_at", "id").values_list("pk", flat=True)[:batch_size]
    processed = 0
    for event_id in event_ids:
        try:
            processed += bool(process_event(event_id))
        except EnrollmentSyncEvent.DoesNotExist:
            continue
        except Exception:
            logger.exception("Enrollment outbox event %s remains pending for retry.", event_id)
    return processed
