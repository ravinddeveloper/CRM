"""Idempotently copy legacy SQL audit history into MongoDB."""
from django.core.management.base import BaseCommand, CommandError

from apps.audit.models import AuditLog
from apps.audit.repositories.mongo import MongoAuditLogRepository
from infrastructure.database.config import DatabaseEngine, get_database_engine


class Command(BaseCommand):
    help = "Copy existing SQL audit logs to MongoDB before selecting the Mongo audit repository."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=500)

    def handle(self, *args, **options):
        if get_database_engine() is not DatabaseEngine.SQL:
            raise CommandError("Run the audit history snapshot with DATABASE_ENGINE=sql.")
        batch_size = options["batch_size"]
        if batch_size < 1:
            raise CommandError("--batch-size must be greater than zero.")
        repository = MongoAuditLogRepository()
        imported = 0
        for record in AuditLog.objects.select_related("actor").order_by("created_at", "id").iterator(
            chunk_size=batch_size
        ):
            imported += bool(repository.import_sql_record(record))
        self.stdout.write(self.style.SUCCESS(f"Imported {imported} audit records into MongoDB."))
