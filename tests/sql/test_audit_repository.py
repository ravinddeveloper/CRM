import pytest
from django.test import TestCase

from apps.audit.models import AuditAction, AuditLog
from apps.audit.repositories.sql import SQLAuditLogRepository
from tests.factories import make_student


@pytest.mark.django_db
class SQLAuditLogRepositoryTests(TestCase):
    def test_create_and_recent_list_preserve_actor_and_audit_fields(self):
        actor = make_student()
        repository = SQLAuditLogRepository()

        created = repository.create(
            actor_id=str(actor.pk), actor_email=actor.email,
            action=AuditAction.ROLE_CHANGED, object_type="User", object_id=str(actor.pk),
            object_repr=actor.email, changes={"from": "student", "to": "teacher"},
            ip_address="192.0.2.6",
        )
        listed = repository.list_recent(action=AuditAction.ROLE_CHANGED, limit=10)

        self.assertTrue(AuditLog.objects.filter(pk=created.pk).exists())
        self.assertEqual(listed[0].actor.email, actor.email)
        self.assertEqual(listed[0].changes["to"], "teacher")

    def test_model_convenience_logger_uses_the_selected_repository(self):
        actor = make_student()

        log = AuditLog.log(AuditAction.USER_LOGIN, actor=actor, ip="192.0.2.7")

        self.assertTrue(AuditLog.objects.filter(pk=log.pk, action=AuditAction.USER_LOGIN).exists())
