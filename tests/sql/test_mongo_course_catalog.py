import pytest

from apps.courses.repositories.mongo import MongoCourseCatalogRepository
from apps.courses.serializers import CourseDetailSerializer
from tests.factories import make_category, make_course, make_lecture, make_section

pytestmark = pytest.mark.django_db


class FakeCollection:
    def __init__(self):
        self.update = None

    def create_index(self, *args, **kwargs):
        return None

    def update_one(self, query, update, **kwargs):
        self.update = (query, update, kwargs)


class FakeDatabase:
    def __init__(self):
        self.collection = FakeCollection()

    def __getitem__(self, name):
        assert name == "course_catalog"
        return self.collection


def test_course_catalog_mongo_projection_keeps_api_fields_and_revision():
    category = make_category(name="Science")
    course = make_course(category=category, title="Catalog mapping")
    database = FakeDatabase()
    repository = MongoCourseCatalogRepository(database=database)

    repository.sync_sql_course(course, source_revision=71)

    query, pipeline, kwargs = database.collection.update
    assert query == {"public_id": str(course.pk)}
    assert kwargs["upsert"] is True
    condition = pipeline[0]["$replaceWith"]["$cond"]
    assert condition[0] == {"$gt": [71, {"$ifNull": ["$source_revision", -1]}]}
    document = condition[1]["$mergeObjects"][1]
    assert document["id"] == str(course.pk)
    assert document["category"]["slug"] == category.slug
    assert document["teacher_name"] == course.teacher.full_name
    assert document["price"] == str(course.price)
    assert document["effective_price"] == str(course.effective_price)
    assert document["source_revision"] == 71


def test_course_catalog_records_normalize_mongo_datetime_and_decimal_values():
    from datetime import datetime

    record = MongoCourseCatalogRepository._record({
        "public_id": "id", "id": "id", "created_at": datetime(2026, 1, 1),
        "price": "10.00", "discount_price": None, "effective_price": "10.00",
        "deleted": False, "source_revision": 2,
    })

    assert record["price"] == "10.00"
    assert record["created_at"].utcoffset().total_seconds() == 0
    assert "source_revision" not in record


def test_mongo_catalog_document_has_the_existing_course_detail_api_shape():
    course = make_course(title="Detail projection")
    course.teacher.profile.bio = "Instructor details"
    course.teacher.profile.save(update_fields=["bio", "updated_at"])
    section = make_section(course=course)
    lecture = make_lecture(section=section)
    document = MongoCourseCatalogRepository._sql_document(course)

    response = CourseDetailSerializer(MongoCourseCatalogRepository._record(document)).data

    assert response["id"] == str(course.pk)
    assert response["teacher_name"] == course.teacher.full_name
    assert response["teacher_bio"] == "Instructor details"
    assert response["sections"][0]["id"] == str(section.pk)
    assert response["sections"][0]["lectures"][0]["id"] == str(lecture.pk)
