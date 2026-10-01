"""SQL audit log adapter."""
from django.db import DatabaseError

from apps.audit.models import AuditLog
from infrastructure.database.exceptions import DatabaseConnectionError


class SQLAuditLogRepository:
    def create(self, **values):
        actor_id = values.pop("actor_id", None)
        values.pop("actor_email", None)
        try:
            return AuditLog.objects.create(actor_id=actor_id, **values)
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not write the audit event.") from exc

    def list_recent(self, *, action=None, limit=150):
        try:
            rows = AuditLog.objects.select_related("actor").order_by("-created_at", "-id")
            if action:
                rows = rows.filter(action=action)
            return list(rows[:limit])
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not list audit events.") from exc
