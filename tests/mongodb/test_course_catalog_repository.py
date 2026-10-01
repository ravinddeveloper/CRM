import os
from uuid import uuid4

import pytest
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    pytest.skip("Set MONGO_URI to run MongoDB integration tests.", allow_module_level=True)

from pymongo import MongoClient

from apps.courses.repositories.mongo import MongoCourseCatalogRepository
from apps.courses.serializers import CourseDetailSerializer
from tests.factories import make_category, make_course, make_lecture, make_section

pytestmark = pytest.mark.django_db


@pytest.fixture
def repository():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
    database = client[f"test_course_catalog_{uuid4().hex}"]
    try:
        yield MongoCourseCatalogRepository(database=database)
    finally:
        client.drop_database(database.name)
        client.close()


def test_catalog_projection_filters_published_courses_and_applies_revisions(repository):
    category = make_category(name=f"Catalog {uuid4().hex[:7]}")
    course = make_course(category=category, title=f"Catalog course {uuid4().hex[:7]}")
    course.teacher.profile.bio = "Mongo catalog bio"
    course.teacher.profile.save(update_fields=["bio", "updated_at"])
    course.tags.create(name=f"Tag {uuid4().hex[:7]}")
    section = make_section(course=course)
    lecture = make_lecture(section=section)

    repository.sync_sql_course(course, source_revision=10)
    count, records = repository.list_published(
        category=category.slug, search="Catalog course", difficulty=course.difficulty,
        is_free=False, limit=10, offset=0,
    )

    assert count == 1
    assert records[0]["id"] == str(course.pk)
    assert records[0]["category"]["slug"] == category.slug
    detail = CourseDetailSerializer(repository.get_by_id(course.pk)).data
    assert detail["teacher_bio"] == "Mongo catalog bio"
    assert detail["tags"][0]["name"].startswith("Tag ")
    assert detail["sections"][0]["lectures"][0]["id"] == str(lecture.pk)

    course.title = "Updated catalog title"
    course.save(update_fields=["title", "updated_at"])
    repository.sync_sql_course(course, source_revision=12)
    repository.sync_sql_course(course, source_revision=11)
    _, updated = repository.list_published(
        category=category.slug, search="Updated catalog title", difficulty=None,
        is_free=None, limit=10, offset=0,
    )
    assert len(updated) == 1
    assert updated[0]["title"] == "Updated catalog title"

    repository.delete_by_id(course.pk, source_revision=13)
    count, _ = repository.list_published(
        category=None, search="Updated catalog title", difficulty=None,
        is_free=None, limit=10, offset=0,
    )
    assert count == 0
