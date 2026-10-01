import os
from uuid import uuid4

import pytest

MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    pytest.skip("Set MONGO_URI to run MongoDB integration tests.", allow_module_level=True)

pytest.importorskip("pymongo")
from pymongo import MongoClient

from apps.analytics.repositories.mongo import MongoCourseViewRepository


@pytest.fixture
def repository():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
    database = client[f"test_analytics_{uuid4().hex}"]
    try:
        yield MongoCourseViewRepository(database=database)
    finally:
        client.drop_database(database.name)
        client.close()


def test_course_view_is_stored_as_a_document_with_scalar_relationship_ids(repository):
    record = repository.record_view(
        course_id="course-uuid", user_id="user-uuid", ip_address="192.0.2.4", session_key="session-1"
    )

    assert record.course_id == "course-uuid"
    assert record.user_id == "user-uuid"
    assert repository.collection.find_one({"public_id": record.id})["_id"] is not None
    assert repository.get_total_views(course_id="course-uuid") == 1


def test_legacy_counter_seed_does_not_overwrite_live_mongo_views(repository):
    repository.record_view(
        course_id="course-uuid", user_id=None, ip_address=None, session_key="session-1"
    )
    repository.import_sql_course_count(course_id="course-uuid", total_views=23)

    counter = repository.counter_collection.find_one({"course_id": "course-uuid"})
    assert counter["legacy_total_views"] == 0
    assert repository.get_total_views(course_id="course-uuid") == 1


def test_legacy_counter_seed_preserves_existing_sql_total(repository):
    repository.import_sql_course_count(course_id="course-uuid", total_views=23)

    counter = repository.counter_collection.find_one({"course_id": "course-uuid"})
    assert counter["legacy_total_views"] == 23
    assert repository.get_total_views(course_id="course-uuid") == 23
