"""Drain pending SQL identity projections into MongoDB."""
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import AccountSyncEvent
from apps.accounts.tasks import process_event
from infrastructure.database.config import DatabaseEngine, get_database_engine


class Command(BaseCommand):
    help = "Drain pending SQL account outbox events into MongoDB."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=500)

    def handle(self, *args, **options):
        if get_database_engine() is not DatabaseEngine.MONGODB:
            raise CommandError("Select DATABASE_ENGINE=mongodb before draining account sync events.")
        batch_size = options["batch_size"]
        if not 1 <= batch_size <= 5000:
            raise CommandError("--batch-size must be between 1 and 5000.")

        processed = 0
        max_event_id = AccountSyncEvent.objects.order_by("-id").values_list("pk", flat=True).first()
        if max_event_id is not None:
            while True:
                event_ids = list(AccountSyncEvent.objects.filter(
                    processed_at__isnull=True, pk__lte=max_event_id
                ).order_by("created_at", "id").values_list("pk", flat=True)[:batch_size])
                if not event_ids:
                    break
                for event_id in event_ids:
                    processed += bool(process_event(event_id))
        self.stdout.write(self.style.SUCCESS(f"Processed {processed} account sync events."))
