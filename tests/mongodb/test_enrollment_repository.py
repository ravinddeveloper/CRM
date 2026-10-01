import os
from uuid import uuid4

import pytest

MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    pytest.skip("Set MONGO_URI to run MongoDB integration tests.", allow_module_level=True)

pytest.importorskip("pymongo")
from pymongo import MongoClient

from apps.enrollments.repositories.mongo import MongoEnrollmentRepository
from tests.factories import make_course, make_enrollment, make_student

pytestmark = pytest.mark.django_db


@pytest.fixture
def repository():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
    database = client[f"test_enrollments_{uuid4().hex}"]
    try:
        yield MongoEnrollmentRepository(database=database)
    finally:
        client.drop_database(database.name)
        client.close()


def test_import_is_idempotent_and_list_is_user_scoped(repository):
    student = make_student()
    course = make_course(status="published")
    enrollment = make_enrollment(user=student, course=course)

    assert repository.import_sql_record(enrollment) is True
    assert repository.import_sql_record(enrollment) is False
    count, records = repository.list_for_user(user_id=str(student.pk), limit=20, offset=0)
    other_count, other_records = repository.list_for_user(user_id="another-user", limit=20, offset=0)

    assert count == 1
    assert len(records) == 1
    assert records[0].id == str(enrollment.pk)
    assert records[0].course_id == str(course.pk)
    assert other_count == 0
    assert other_records == []


@pytest.mark.django_db
def test_tombstone_prevents_stale_snapshot_or_event_from_resurrecting_deleted_row(repository):
    student = make_student()
    course = make_course(status="published")
    enrollment = make_enrollment(user=student, course=course)

    repository.import_sql_record(enrollment)
    repository.delete_by_id(enrollment.pk, source_revision=20)
    assert repository.import_sql_record(enrollment) is False
    repository.sync_sql_record(enrollment, source_revision=19)

    assert repository.list_for_user(user_id=str(student.pk), limit=20, offset=0) == (0, [])
