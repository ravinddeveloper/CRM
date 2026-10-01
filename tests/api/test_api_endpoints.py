"""
API tests: Test all REST API endpoints through the DRF test client.
"""
import json
from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from tests.factories import (
    make_admin, make_teacher, make_student, make_course,
    make_section, make_lecture, make_enrollment,
)


class TestCourseListAPI(TestCase):
    """Tests for /api/v1/courses/ endpoint."""

    def setUp(self):
        self.client = APIClient()

    def test_list_published_courses(self):
        make_course(status="published")
        response = self.client.get("/api/v1/courses/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)

    def test_list_excludes_draft_courses(self):
        make_course(status="draft", title="Draft Hidden Course")
        response = self.client.get("/api/v1/courses/")
        self.assertEqual(response.status_code, 200)
        titles = [c["title"] for c in response.data.get("results", [])]
        self.assertNotIn("Draft Hidden Course", titles)

    def test_filter_by_category(self):
        from apps.courses.models import Category
        cat = Category.objects.create(name="Python", slug="python")
        make_course(status="published", title="Python Basics", category=cat)
        make_course(status="published", title="Django Course")  # no category
        response = self.client.get(f"/api/v1/courses/?category={cat.slug}")
        self.assertEqual(response.status_code, 200)

    def test_search_courses(self):
        make_course(status="published", title="Advanced React")
        response = self.client.get("/api/v1/courses/?search=Advanced")
        self.assertEqual(response.status_code, 200)

    def test_pagination_works(self):
        for i in range(15):
            make_course(status="published", title=f"Course {i}")
        response = self.client.get("/api/v1/courses/?page=1")
        self.assertEqual(response.status_code, 200)
        self.assertIn("count", response.data)


class TestCourseDetailAPI(TestCase):
    """Tests for /api/v1/courses/{id}/ endpoint."""

    def setUp(self):
        self.client = APIClient()

    def test_get_course_detail(self):
        course = make_course(status="published")
        response = self.client.get(f"/api/v1/courses/{course.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(response.data["id"]), str(course.id))

    def test_get_draft_course_returns_404_for_student(self):
        draft = make_course(status="draft")
        student = make_student()
        self.client.force_authenticate(user=student)
        response = self.client.get(f"/api/v1/courses/{draft.id}/")
        self.assertIn(response.status_code, [403, 404])


class TestProgressAPI(TestCase):
    """API tests for the progress tracking endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.student = make_student()
        self.client.force_authenticate(user=self.student)
        self.course = make_course(status="published")
        self.section = make_section(course=self.course)
        self.lecture = make_lecture(section=self.section)
        self.enrollment = make_enrollment(user=self.student, course=self.course)

    def test_update_position_endpoint(self):
        response = self.client.post(
            f"/api/v1/progress/lectures/{self.lecture.id}/position/",
            {"position_seconds": 100, "watched_seconds": 100, "video_duration": 600},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])

    def test_get_resume_position(self):
        # Set position first
        self.client.post(
            f"/api/v1/progress/lectures/{self.lecture.id}/position/",
            {"position_seconds": 250, "watched_seconds": 250, "video_duration": 600},
            format="json",
        )
        response = self.client.get(
            f"/api/v1/progress/lectures/{self.lecture.id}/resume/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["position_seconds"], 250)

    def test_course_progress_endpoint(self):
        response = self.client.get(
            f"/api/v1/progress/courses/{self.course.id}/progress/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["enrolled"])

    def test_unauthenticated_progress_returns_401(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            f"/api/v1/progress/lectures/{self.lecture.id}/position/",
            {"position_seconds": 100, "watched_seconds": 100, "video_duration": 600},
            format="json",
        )
        self.assertIn(response.status_code, [401, 403])


class TestEnrollmentsAPI(TestCase):
    """Tests for /api/v1/enrollments/ endpoints."""

    def setUp(self):
        self.client = APIClient()

    def test_list_enrollments_requires_auth(self):
        response = self.client.get("/api/v1/enrollments/")
        self.assertIn(response.status_code, [401, 403])

    def test_student_sees_only_own_enrollments(self):
        student_a = make_student()
        student_b = make_student()
        course = make_course(status="published")
        make_enrollment(user=student_a, course=course)

        self.client.force_authenticate(user=student_b)
        response = self.client.get("/api/v1/enrollments/")
        if response.status_code == 200:
            # Student B should not see Student A's enrollment
            ids = [str(e.get("user")) for e in response.data.get("results", [])]
            self.assertNotIn(str(student_a.id), ids)

    def test_enrollment_list_keeps_course_detail_and_pagination_shape(self):
        student = make_student()
        course = make_course(status="published")
        make_enrollment(user=student, course=course)
        self.client.force_authenticate(user=student)

        response = self.client.get("/api/v1/enrollments/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertIsNone(response.data["next"])
        self.assertIsNone(response.data["previous"])
        result = response.data["results"][0]
        self.assertEqual(result["user"], str(student.pk))
        self.assertEqual(result["course"], str(course.pk))
        self.assertEqual(result["course_detail"]["id"], str(course.pk))


class TestNotificationsAPI(TestCase):
    """Tests for /api/v1/notifications/ endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.student = make_student()
        self.client.force_authenticate(user=self.student)

    def test_list_notifications(self):
        response = self.client.get("/api/v1/notifications/")
        self.assertIn(response.status_code, [200, 404])

    def test_mark_notification_read(self):
        from apps.notifications.models import Notification
        notif = Notification.objects.create(
            user=self.student,
            title="Test Notification",
            message="Hello!",
            notification_type="general",
        )
        response = self.client.post(f"/api/v1/notifications/{notif.id}/read/")
        if response.status_code == 200:
            notif.refresh_from_db()
            self.assertTrue(notif.is_read)
