"""Idempotently copy legacy SQL enrollments into MongoDB."""
from django.core.management.base import BaseCommand, CommandError

from apps.enrollments.models import Enrollment, EnrollmentSyncEvent
from apps.enrollments.repositories.mongo import MongoEnrollmentRepository
from apps.enrollments.tasks import process_event
from infrastructure.database.config import DatabaseEngine, get_database_engine


class Command(BaseCommand):
    help = "Copy SQL enrollments to MongoDB before switching the enrollment listing repository."

    def add_arguments(self, parser):
        parser.add_argument(
            "--drain-outbox", action="store_true",
            help="Process pending incremental synchronization events as well as the initial snapshot.",
        )

    def handle(self, *args, **options):
        repository = MongoEnrollmentRepository()
        if get_database_engine() is DatabaseEngine.SQL:
            count = 0
            for enrollment in Enrollment.objects.order_by("created_at", "id").iterator(chunk_size=500):
                if repository.import_sql_record(enrollment):
                    count += 1
            self.stdout.write(self.style.SUCCESS(f"Imported {count} enrollment records into MongoDB."))
        elif not options["drain_outbox"]:
            raise CommandError("Run the initial snapshot with DATABASE_ENGINE=sql; Mongo mode supports --drain-outbox only.")

        if options["drain_outbox"]:
            processed = 0
            max_event_id = EnrollmentSyncEvent.objects.order_by("-id").values_list("pk", flat=True).first()
            if max_event_id is not None:
                while True:
                    event_ids = list(EnrollmentSyncEvent.objects.filter(
                        processed_at__isnull=True, pk__lte=max_event_id
                    ).order_by("created_at", "id").values_list("pk", flat=True)[:500])
                    if not event_ids:
                        break
                    for event_id in event_ids:
                        processed += bool(process_event(event_id))
            self.stdout.write(self.style.SUCCESS(f"Processed {processed} pending enrollment sync events."))
