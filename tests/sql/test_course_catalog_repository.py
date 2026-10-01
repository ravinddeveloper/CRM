import pytest

from apps.courses.repositories.sql import SQLCourseCatalogRepository
from apps.courses.models import Tag
from tests.factories import make_category, make_course, make_lecture, make_section, make_teacher

pytestmark = pytest.mark.django_db


def test_catalog_sql_repository_filters_price_and_sorts_numerically():
    cheap = make_course(title="Budget", price="15.00")
    middle = make_course(title="Midrange", price="80.00")
    expensive = make_course(title="Premium", price="320.00")
    repository = SQLCourseCatalogRepository()

    count, courses = repository.list_published(
        category=None, search="", difficulty=None, is_free=None,
        price_min="50", price_max="350", sort="price_low", limit=12, offset=0,
    )

    assert count == 2
    assert [course["id"] for course in courses] == [str(middle.pk), str(expensive.pk)]
    assert str(cheap.pk) not in [course["id"] for course in courses]


def test_catalog_sql_repository_can_match_teacher_and_tag_searches():
    teacher = make_teacher(first_name="Searchable")
    tagged = make_course(teacher=teacher, title="Unrelated title")
    tagged.tags.add(Tag.objects.create(name="Flamenco") )
    category = make_category()
    make_course(category=category, title="Different")
    repository = SQLCourseCatalogRepository()

    _, teacher_matches = repository.list_published(
        category=None, search="Searchable", difficulty=None, is_free=None,
        include_related_search=True, limit=12, offset=0,
    )
    _, tag_matches = repository.list_published(
        category=None, search="Flamenco", difficulty=None, is_free=None,
        include_related_search=True, limit=12, offset=0,
    )

    assert [course["id"] for course in teacher_matches] == [str(tagged.pk)]
    assert [course["id"] for course in tag_matches] == [str(tagged.pk)]


def test_catalog_sql_repository_lists_active_categories_and_looks_up_slug():
    parent = make_category(name="Root category")
    from apps.courses.models import Category
    child = Category.objects.create(name="Nested category", parent=parent)
    Category.objects.create(name="Hidden category", is_active=False)
    repository = SQLCourseCatalogRepository()

    categories = repository.list_categories(root_only=True)
    found = repository.get_category_by_slug(child.slug)

    assert [item["slug"] for item in categories] == [parent.slug]
    assert found["name"] == child.name
    assert found["parent_id"] == str(parent.pk)
    assert repository.get_category_by_slug("hidden-category") is None


def test_catalog_sql_repository_reads_complete_published_detail_by_slug():
    course = make_course(title="Repository detail")
    section = make_section(course=course)
    lecture = make_lecture(section=section)

    record = SQLCourseCatalogRepository().get_by_slug(course.slug)

    assert record["id"] == str(course.pk)
    assert record["teacher"]["email"] == course.teacher.email
    assert record["is_published"] is True
    assert record["sections"][0]["id"] == str(section.pk)
    assert record["sections"][0]["lectures"][0]["id"] == str(lecture.pk)
    assert record["total_lectures_count"] == 1
