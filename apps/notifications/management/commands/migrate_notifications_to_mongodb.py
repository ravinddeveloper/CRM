"""Idempotently copy legacy SQL notification rows into MongoDB."""
from django.core.management.base import BaseCommand, CommandError

from apps.notifications.models import Notification, NotificationSyncEvent
from apps.notifications.repositories.mongo import MongoNotificationRepository
from apps.notifications.tasks import process_event
from infrastructure.database.config import DatabaseEngine, get_database_engine


class Command(BaseCommand):
    help = "Copy SQL notification history to MongoDB before changing the notification repository engine."

    def add_arguments(self, parser):
        parser.add_argument(
            "--drain-outbox", action="store_true",
            help="Also apply notification changes captured while the SQL snapshot is copied.",
        )

    def handle(self, *args, **options):
        repository = MongoNotificationRepository()
        if get_database_engine() is DatabaseEngine.SQL:
            count = 0
            for notification in Notification.objects.order_by("created_at", "id").iterator(chunk_size=500):
                if repository.import_sql_record(notification):
                    count += 1
            self.stdout.write(self.style.SUCCESS(f"Imported {count} notification records into MongoDB."))
        elif not options["drain_outbox"]:
            raise CommandError("Run the initial snapshot with DATABASE_ENGINE=sql; Mongo mode supports --drain-outbox only.")

        if options["drain_outbox"]:
            processed = 0
            max_event_id = NotificationSyncEvent.objects.order_by("-id").values_list("pk", flat=True).first()
            if max_event_id is not None:
                while True:
                    event_ids = list(NotificationSyncEvent.objects.filter(
                        processed_at__isnull=True, pk__lte=max_event_id
                    ).order_by("created_at", "id").values_list("pk", flat=True)[:500])
                    if not event_ids:
                        break
                    for event_id in event_ids:
                        processed += bool(process_event(event_id))
            self.stdout.write(self.style.SUCCESS(f"Processed {processed} pending notification sync events."))
