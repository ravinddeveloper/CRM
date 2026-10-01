"""Backfill published-course API projections into MongoDB."""
from django.core.management.base import BaseCommand, CommandError

from apps.courses.models import Course, CourseCatalogSyncEvent
from apps.courses.repositories.mongo import MongoCourseCatalogRepository
from apps.courses.tasks import process_catalog_event
from infrastructure.database.config import DatabaseEngine, get_database_engine


class Command(BaseCommand):
    help = "Copy SQL course catalog rows to MongoDB, optionally draining concurrent changes."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=250)
        parser.add_argument("--drain-outbox", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        if not 1 <= batch_size <= 5000:
            raise CommandError("--batch-size must be between 1 and 5000.")
        if options["dry_run"]:
            if options["drain_outbox"]:
                raise CommandError("--dry-run cannot be combined with --drain-outbox.")
            count = Course.objects.count()
            self.stdout.write(self.style.SUCCESS(f"Dry run: {count} courses are available for projection."))
            return
        if not options["drain_outbox"] and get_database_engine() is not DatabaseEngine.SQL:
            raise CommandError("Run the initial SQL snapshot while DATABASE_ENGINE=sql.")

        try:
            repository = MongoCourseCatalogRepository()
            imported = sum(
                bool(repository.import_sql_course(course))
                for course in Course.objects.select_related(
                    "category", "teacher", "teacher__profile"
                ).prefetch_related("tags", "sections__lectures").order_by("pk").iterator(chunk_size=batch_size)
            )
        except Exception as exc:
            raise CommandError("Course catalog snapshot failed; it is safe to rerun after fixing MongoDB.") from exc

        processed = 0
        if options["drain_outbox"]:
            max_event_id = CourseCatalogSyncEvent.objects.order_by("-id").values_list("pk", flat=True).first()
            if max_event_id is not None:
                while True:
                    event_ids = list(CourseCatalogSyncEvent.objects.filter(
                        processed_at__isnull=True, pk__lte=max_event_id
                    ).order_by("created_at", "id").values_list("pk", flat=True)[:batch_size])
                    if not event_ids:
                        break
                    for event_id in event_ids:
                        processed += bool(process_catalog_event(event_id))
        self.stdout.write(self.style.SUCCESS(
            f"Course catalog snapshot complete: {imported} inserted, {processed} outbox events processed."
        ))
