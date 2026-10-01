import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.utils import timezone
from unittest.mock import patch

from apps.accounts.models import AccountSyncEvent, EmailVerificationToken
from apps.accounts.tasks import process_event

pytestmark = pytest.mark.django_db


def test_account_outbox_captures_profile_token_and_security_changes(monkeypatch):
    monkeypatch.setenv("MONGO_ACCOUNT_SYNC_ENABLED", "true")
    user = get_user_model().objects.create_user(
        email="sync@example.com", username="sync-user", password="secret"
    )
    initial = AccountSyncEvent.objects.filter(account_id=user.pk, event_type=AccountSyncEvent.UPSERT).count()
    assert initial >= 1

    user.is_suspended = True
    user.suspended_reason = "review"
    user.suspended_at = timezone.now()
    user.save(update_fields=["is_suspended", "suspended_reason", "suspended_at"])
    user.profile.bio = "Updated profile"
    user.profile.save(update_fields=["bio", "updated_at"])
    token = EmailVerificationToken.objects.create(user=user)
    token.mark_used()

    assert AccountSyncEvent.objects.filter(
        account_id=user.pk, event_type=AccountSyncEvent.UPSERT
    ).count() >= initial + 4


def test_account_outbox_tracks_permission_grants_and_delete(monkeypatch):
    monkeypatch.setenv("MONGO_ACCOUNT_SYNC_ENABLED", "true")
    User = get_user_model()
    user = User.objects.create_user(email="grants@example.com", username="grant-user", password="secret")
    group = Group.objects.create(name="sync group")
    permission = Permission.objects.order_by("pk").first()
    if permission is not None:
        group.permissions.add(permission)
        user.groups.add(group)
        prior_count = AccountSyncEvent.objects.filter(account_id=user.pk).count()
        user.groups.clear()
        assert AccountSyncEvent.objects.filter(account_id=user.pk).count() > prior_count

    account_id = user.pk
    user.delete()
    assert AccountSyncEvent.objects.filter(
        account_id=account_id, event_type=AccountSyncEvent.DELETE
    ).exists()


def test_account_outbox_worker_projects_current_record_with_monotonic_revision(monkeypatch):
    monkeypatch.setenv("MONGO_ACCOUNT_SYNC_ENABLED", "true")
    user = get_user_model().objects.create_user(
        email="worker@example.com", username="worker-user", password="secret"
    )
    event = AccountSyncEvent.objects.create(account_id=user.pk, event_type=AccountSyncEvent.UPSERT)
    user.first_name = "Current"
    user.save(update_fields=["first_name"])

    with patch("apps.accounts.tasks.MongoAccountRepository") as repository_class:
        assert process_event(event.pk) is True

    repository_class.return_value.import_sql_record.assert_called_once()
    call = repository_class.return_value.import_sql_record.call_args
    assert call.args[0].first_name == "Current"
    assert call.kwargs["source_revision"] == event.pk
    event.refresh_from_db()
    assert event.processed_at is not None
