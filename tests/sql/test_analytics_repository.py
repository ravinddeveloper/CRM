import pytest
from django.test import TestCase

from apps.analytics.models import CourseView
from apps.analytics.repositories.sql import SQLCourseViewRepository
from tests.factories import make_course, make_student


@pytest.mark.django_db
class SQLCourseViewRepositoryTests(TestCase):
    def test_record_view_returns_backend_neutral_record(self):
        course = make_course()
        user = make_student()

        record = SQLCourseViewRepository().record_view(
            course_id=str(course.id), user_id=str(user.id), ip_address="192.0.2.4", session_key="session-1"
        )

        self.assertIsInstance(record.id, str)
        self.assertEqual(record.course_id, str(course.id))
        self.assertEqual(record.user_id, str(user.id))
        self.assertTrue(CourseView.objects.filter(pk=record.id).exists())
        course.refresh_from_db()
        self.assertEqual(course.total_views, 1)
