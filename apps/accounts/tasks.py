"""Retryable SQL-to-Mongo account projection tasks."""
import logging

from celery import shared_task
from decouple import config
from django.utils import timezone

from infrastructure.database.config import DatabaseEngine, get_database_engine

from .models import AccountSyncEvent
from .repositories.mongo import MongoAccountRepository

logger = logging.getLogger("apps.accounts")


def process_event(event_id):
    event = AccountSyncEvent.objects.filter(pk=event_id, processed_at__isnull=True).first()
    if event is None:
        return False
    try:
        if event.event_type == AccountSyncEvent.DELETE:
            MongoAccountRepository().delete_by_id(event.account_id, source_revision=event.pk)
        else:
            from django.contrib.auth import get_user_model
            user = get_user_model().objects.filter(pk=event.account_id).first()
            repository = MongoAccountRepository()
            if user is None:
                repository.delete_by_id(event.account_id, source_revision=event.pk)
            else:
                repository.import_sql_record(user, source_revision=event.pk)
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
def process_account_sync_event(self, event_id):
    try:
        process_event(event_id)
    except AccountSyncEvent.DoesNotExist:
        logger.info("Account sync event %s was already removed or processed.", event_id)
    except Exception as exc:
        raise self.retry(exc=exc, countdown=min(30 * (2 ** self.request.retries), 1800))


@shared_task(ignore_result=True)
def drain_pending_account_sync_events(batch_size=200):
    enabled = config("MONGO_ACCOUNT_SYNC_ENABLED", default=False, cast=bool)
    if get_database_engine() is not DatabaseEngine.MONGODB and not enabled:
        return 0
    event_ids = AccountSyncEvent.objects.filter(
        processed_at__isnull=True
    ).order_by("created_at", "id").values_list("pk", flat=True)[:batch_size]
    processed = 0
    for event_id in event_ids:
        try:
            processed += bool(process_event(event_id))
        except AccountSyncEvent.DoesNotExist:
            continue
        except Exception:
            logger.exception("Account sync event %s remains pending for retry.", event_id)
    return processed
