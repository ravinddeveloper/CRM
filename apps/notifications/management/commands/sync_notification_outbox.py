"""Retry pending SQL notification projections while MongoDB is selected."""
from django.core.management.base import BaseCommand, CommandError

from apps.notifications.models import NotificationSyncEvent
from apps.notifications.tasks import process_event
from infrastructure.database.config import DatabaseEngine, get_database_engine


class Command(BaseCommand):
    help = "Drain pending SQL outbox events into MongoDB after enabling the Mongo repository engine."

    def handle(self, *args, **options):
        if get_database_engine() is not DatabaseEngine.MONGODB:
            raise CommandError("Select DATABASE_ENGINE=mongodb before draining notification sync events.")

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
        self.stdout.write(self.style.SUCCESS(f"Processed {processed} notification sync events."))
