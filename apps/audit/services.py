"""Application service for backend-neutral audit writes and reads."""
from infrastructure.database.factory import get_audit_log_repository


class AuditLogService:
    @staticmethod
    def create(*, actor=None, **values):
        values["actor_id"] = str(actor.pk) if actor is not None else None
        values["actor_email"] = getattr(actor, "email", "") if actor is not None else ""
        return get_audit_log_repository().create(**values)

    @staticmethod
    def list_recent(*, action=None, limit=150):
        return get_audit_log_repository().list_recent(action=action, limit=limit)
