"""Copy existing SQL accounts into MongoDB in resumable batches."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.repositories.mongo import MongoAccountRepository


class Command(BaseCommand):
    help = "Copy SQL account and authentication state into MongoDB without changing SQL data."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=250)
        parser.add_argument(
            "--drain-outbox", action="store_true",
            help="Also process account changes captured in the SQL outbox during/after the snapshot.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report the number of SQL accounts without connecting to MongoDB or importing them.",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        if not 1 <= batch_size <= 5000:
            raise CommandError("--batch-size must be between 1 and 5000.")

        User = get_user_model()
        queryset = User.objects.order_by("pk")
        if options["dry_run"]:
            if options["drain_outbox"]:
                raise CommandError("--dry-run cannot be combined with --drain-outbox.")
            self.stdout.write(self.style.SUCCESS(
                f"Dry run: {queryset.count()} SQL accounts are available for import."
            ))
            return

        imported = 0
        existing = 0
        try:
            repository = MongoAccountRepository()
            for user in queryset.iterator(chunk_size=batch_size):
                if repository.import_sql_record(user):
                    imported += 1
                else:
                    existing += 1
        except Exception as exc:
            raise CommandError(
                f"Account import stopped after {imported if 'imported' in locals() else 0} new records; "
                "rerun the command after fixing MongoDB connectivity."
            ) from exc

        outbox_processed = 0
        if options["drain_outbox"]:
            from apps.accounts.models import AccountSyncEvent
            from apps.accounts.tasks import process_event

            max_event_id = AccountSyncEvent.objects.order_by("-id").values_list("pk", flat=True).first()
            if max_event_id is not None:
                while True:
                    event_ids = list(AccountSyncEvent.objects.filter(
                        processed_at__isnull=True, pk__lte=max_event_id
                    ).order_by("created_at", "id").values_list("pk", flat=True)[:batch_size])
                    if not event_ids:
                        break
                    for event_id in event_ids:
                        outbox_processed += bool(process_event(event_id))

        self.stdout.write(self.style.SUCCESS(
            f"Account snapshot finished: {imported} imported, {existing} already present, "
            f"{outbox_processed} outbox events processed. SQL remains authoritative; "
            "MongoDB authentication and Django-dependent account flows remain SQL-backed."
        ))
