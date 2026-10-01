import os
from datetime import timezone
from uuid import uuid4

import pytest

MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    pytest.skip("Set MONGO_URI to run MongoDB integration tests.", allow_module_level=True)

pytest.importorskip("pymongo")
from pymongo import MongoClient

from apps.analytics.models import CourseView
from apps.analytics.repositories.mongo import MongoCourseViewRepository
from tests.factories import make_course, make_student

pytestmark = pytest.mark.django_db


@pytest.fixture
def repository():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
    database = client[f"test_course_views_{uuid4().hex}"]
    try:
        yield MongoCourseViewRepository(database=database)
    finally:
        client.drop_database(database.name)
        client.close()


def test_course_view_history_import_preserves_sql_fields_and_is_idempotent(repository):
    user = make_student()
    course = make_course(status="published")
    view = CourseView.objects.create(
        course=course, user=user, ip_address="192.0.2.12", session_key="history-session"
    )

    assert repository.import_sql_record(view) is True
    assert repository.import_sql_record(view) is False
    document = repository.collection.find_one({"public_id": str(view.pk)})

    assert document["course_id"] == str(course.pk)
    assert document["user_id"] == str(user.pk)
    assert document["ip_address"] == "192.0.2.12"
    assert document["session_key"] == "history-session"
    stored_at = document["created_at"]
    if stored_at.tzinfo is None:
        stored_at = stored_at.replace(tzinfo=timezone.utc)
    # BSON dates have millisecond precision; SQL timestamps may retain microseconds.
    assert abs((stored_at - view.created_at).total_seconds()) < 0.001
