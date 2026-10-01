import pytest
from django.test import TestCase
from rest_framework.test import APIClient

from apps.notifications.models import Notification, NotificationSyncEvent
from apps.notifications.repositories.sql import SQLNotificationRepository
from infrastructure.database.config import DatabaseEngine
from tests.factories import make_student


@pytest.mark.django_db
class SQLNotificationRepositoryTests(TestCase):
    def setUp(self):
        self.user = make_student()
        self.repository = SQLNotificationRepository()

    def test_create_list_mark_read_and_user_isolation(self):
        record = self.repository.create(
            user_id=str(self.user.id), notification_type="system", title="Notice",
            message="A platform notice.", action_url="/dashboard/",
        )
        count, records = self.repository.list_for_user(user_id=str(self.user.id), limit=20, offset=0)
        self.assertEqual(count, 1)
        self.assertEqual(records[0], record)
        other_user = make_student()
        self.assertEqual(self.repository.list_for_user(user_id=str(other_user.id), limit=20, offset=0), (0, []))

        updated = self.repository.mark_read(notification_id=record.id, user_id=str(self.user.id))
        self.assertTrue(updated.is_read)
        self.assertIsNotNone(updated.read_at)
        self.assertTrue(Notification.objects.get(pk=record.id).is_read)

    def test_api_keeps_paginated_response_shape(self):
        self.repository.create(
            user_id=str(self.user.id), notification_type="system", title="Notice",
            message="A platform notice.", action_url="/dashboard/",
        )
        client = APIClient()
        client.force_authenticate(user=self.user)

        response = client.get("/api/v1/notifications/?page=1&page_size=5")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.data),
            {"success", "count", "next", "previous", "total_pages", "current_page", "results"},
        )
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["notification_type"], "system")

        notification_id = response.data["results"][0]["id"]
        marked = client.post(f"/api/v1/notifications/{notification_id}/read/")
        self.assertEqual(marked.status_code, 200)
        self.assertEqual(marked.data, {"status": "success", "is_read": True})


@pytest.mark.django_db
def test_mongo_projection_outbox_tracks_notification_save_update_and_delete():
    from unittest.mock import patch

    user = make_student()
    with patch("apps.notifications.signals.get_database_engine", return_value=DatabaseEngine.MONGODB):
        notification = Notification.objects.create(
            user=user, notification_type="system", title="Queued", message="Initial",
        )
        notification_id = str(notification.pk)
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        notification.delete()

    events = list(NotificationSyncEvent.objects.order_by("id"))
    assert [event.event_type for event in events] == ["upsert", "upsert", "delete"]
    assert all(str(event.notification_id) == notification_id for event in events)


@pytest.mark.django_db
def test_notification_outbox_projects_latest_state_and_cleans_deleted_records():
    from unittest.mock import patch

    from apps.notifications.tasks import process_event

    user = make_student()
    with patch("apps.notifications.signals.get_database_engine", return_value=DatabaseEngine.MONGODB):
        notification = Notification.objects.create(
            user=user, notification_type="system", title="Queued", message="Initial",
        )
    event = NotificationSyncEvent.objects.filter(notification_id=notification.pk).order_by("id").first()
    with patch("apps.notifications.signals.get_database_engine", return_value=DatabaseEngine.MONGODB):
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    stale_event = NotificationSyncEvent.objects.filter(notification_id=notification.pk).order_by("id").last()

    with patch("apps.notifications.tasks.MongoNotificationRepository") as repository_type:
        process_event(event.pk)
    projected = repository_type.return_value.sync_sql_record.call_args.args[0]
    assert projected.is_read is True

    with patch("apps.notifications.signals.get_database_engine", return_value=DatabaseEngine.MONGODB):
        notification.delete()
    with patch("apps.notifications.tasks.MongoNotificationRepository") as repository_type:
        process_event(stale_event.pk)  # stale upsert must not recreate a deleted notification
    repository_type.return_value.delete_by_id.assert_called_once_with(
        stale_event.notification_id, source_revision=stale_event.pk
    )
