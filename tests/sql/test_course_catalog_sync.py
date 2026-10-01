from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.courses.models import CourseCatalogSyncEvent
from apps.courses.tasks import process_catalog_event
from tests.factories import make_category, make_course, make_lecture, make_section, make_teacher

pytestmark = pytest.mark.django_db


def test_catalog_outbox_tracks_course_category_tags_and_teacher_name(monkeypatch):
    monkeypatch.setenv("MONGO_COURSE_CATALOG_SYNC_ENABLED", "true")
    category = make_category()
    teacher = make_teacher()
    course = make_course(teacher=teacher, category=category)
    initial = CourseCatalogSyncEvent.objects.filter(course_id=course.pk).count()
    assert initial >= 1

    category.name = "Renamed"
    category.save()
    from apps.courses.models import Tag
    course.tags.add(Tag.objects.create(name="Catalog tag"))
    section = make_section(course=course)
    make_lecture(section=section)
    teacher.first_name = "Changed"
    teacher.save(update_fields=["first_name"])
    teacher.profile.bio = "Updated instructor bio"
    teacher.profile.save(update_fields=["bio", "updated_at"])

    assert CourseCatalogSyncEvent.objects.filter(course_id=course.pk).count() >= initial + 6


def test_catalog_worker_projects_current_course_snapshot_with_event_revision(monkeypatch):
    monkeypatch.setenv("MONGO_COURSE_CATALOG_SYNC_ENABLED", "true")
    course = make_course(title="Latest course")
    event = CourseCatalogSyncEvent.objects.create(
        course_id=course.pk, event_type=CourseCatalogSyncEvent.UPSERT
    )

    with patch("apps.courses.tasks.MongoCourseCatalogRepository") as repository_class:
        assert process_catalog_event(event.pk) is True

    repository_class.return_value.sync_sql_course.assert_called_once()
    call = repository_class.return_value.sync_sql_course.call_args
    assert call.args[0].title == "Latest course"
    assert call.kwargs["source_revision"] == event.pk
    event.refresh_from_db()
    assert event.processed_at is not None


def test_catalog_tombstone_worker_for_deleted_course(monkeypatch):
    monkeypatch.setenv("MONGO_COURSE_CATALOG_SYNC_ENABLED", "true")
    course = make_course()
    course_id = course.pk
    course.delete()
    event = CourseCatalogSyncEvent.objects.filter(
        course_id=course_id, event_type=CourseCatalogSyncEvent.DELETE
    ).latest("id")

    with patch("apps.courses.tasks.MongoCourseCatalogRepository") as repository_class:
        assert process_catalog_event(event.pk) is True

    repository_class.return_value.delete_by_id.assert_called_once_with(course_id, source_revision=event.pk)
