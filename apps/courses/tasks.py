"""Retryable SQL-to-Mongo course catalog projection tasks."""
import logging

from celery import shared_task
from decouple import config
from django.utils import timezone

from infrastructure.database.config import DatabaseEngine, get_database_engine

from .models import Course, CourseCatalogSyncEvent
from .repositories.mongo import MongoCourseCatalogRepository

logger = logging.getLogger("apps.courses")


def process_catalog_event(event_id):
    event = CourseCatalogSyncEvent.objects.filter(pk=event_id, processed_at__isnull=True).first()
    if event is None:
        return False
    try:
        repository = MongoCourseCatalogRepository()
        if event.event_type == CourseCatalogSyncEvent.DELETE:
            repository.delete_by_id(event.course_id, source_revision=event.pk)
        else:
            course = Course.objects.select_related("category", "teacher").filter(pk=event.course_id).first()
            if course is None:
                repository.delete_by_id(event.course_id, source_revision=event.pk)
            else:
                repository.sync_sql_course(course, source_revision=event.pk)
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
def process_catalog_sync_event(self, event_id):
    try:
        process_catalog_event(event_id)
    except CourseCatalogSyncEvent.DoesNotExist:
        logger.info("Course catalog event %s was already removed or processed.", event_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=min(30 * (2 ** self.request.retries), 1800))


@shared_task(ignore_result=True)
def drain_pending_catalog_sync_events(batch_size=200):
    sync_enabled = config("MONGO_COURSE_CATALOG_SYNC_ENABLED", default=False, cast=bool)
    if get_database_engine() is not DatabaseEngine.MONGODB and not sync_enabled:
        return 0
    event_ids = CourseCatalogSyncEvent.objects.filter(
        processed_at__isnull=True
    ).order_by("created_at", "id").values_list("pk", flat=True)[:batch_size]
    processed = 0
    for event_id in event_ids:
        try:
            processed += bool(process_catalog_event(event_id))
        except CourseCatalogSyncEvent.DoesNotExist:
            continue
        except Exception:
            logger.exception("Course catalog event %s remains pending for retry.", event_id)
    return processed
