import os
from uuid import uuid4

import pytest

MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    pytest.skip("Set MONGO_URI to run MongoDB integration tests.", allow_module_level=True)

pytest.importorskip("pymongo")
from pymongo import MongoClient

from apps.notifications.repositories.mongo import MongoNotificationRepository
from infrastructure.database.exceptions import EntityNotFoundError


@pytest.fixture
def repository():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
    database = client[f"test_notifications_{uuid4().hex}"]
    try:
        yield MongoNotificationRepository(database=database)
    finally:
        client.drop_database(database.name)
        client.close()


def test_notification_lifecycle_and_user_isolation(repository):
    record = repository.create(
        user_id="user-uuid", notification_type="system", title="Notice",
        message="A platform notice.", action_url="/dashboard/",
    )
    count, records = repository.list_for_user(user_id="user-uuid", limit=20, offset=0)
    assert count == 1
    assert records == [record]
    assert repository.list_for_user(user_id="other-user", limit=20, offset=0) == (0, [])

    updated = repository.mark_read(notification_id=record.id, user_id="user-uuid")
    assert updated.is_read is True
    assert updated.read_at is not None
    assert repository.mark_read(notification_id=record.id, user_id="user-uuid").id == record.id
    with pytest.raises(EntityNotFoundError):
        repository.mark_read(notification_id=record.id, user_id="other-user")


@pytest.mark.django_db
def test_sql_notification_projection_upserts_current_state(repository):
    from apps.notifications.models import Notification
    from tests.factories import make_student

    user = make_student()
    notification = Notification.objects.create(
        user=user, notification_type="system", title="Legacy", message="SQL row",
    )
    repository.sync_sql_record(notification, source_revision=5)
    stored = repository.collection.find_one({"public_id": str(notification.pk)})

    assert stored["user_id"] == str(user.pk)
    assert stored["is_read"] is False
    notification.is_read = True
    repository.sync_sql_record(notification, source_revision=6)
    stored = repository.collection.find_one({"public_id": str(notification.pk)})
    assert stored["is_read"] is True
    repository.delete_by_id(notification.pk, source_revision=9)
    assert repository.import_sql_record(notification) is False
    repository.sync_sql_record(notification, source_revision=8)
    assert repository.list_for_user(user_id=str(user.pk), limit=20, offset=0) == (0, [])
