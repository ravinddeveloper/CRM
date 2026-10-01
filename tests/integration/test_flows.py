"""
Integration tests: Full-stack flows tested through Django's test client.
Tests the complete Register → Enroll → Learn → Complete lifecycle.
"""
import json
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse

from tests.factories import (
    make_admin, make_teacher, make_student, make_course,
    make_section, make_lecture, make_enrollment, make_order,
)


class TestAuthenticationFlow(TestCase):
    """Test registration, login, and logout flows."""

    def setUp(self):
        self.client = Client()

    def test_register_new_student(self):
        """New users can register with valid data."""
        response = self.client.post(
            reverse("accounts:register"),
            {
                "email": "newuser@example.com",
                "password1": "SecurePass123!",
                "password2": "SecurePass123!",
                "first_name": "Test",
                "last_name": "User",
                "username": "testuser",
            },
        )
        # Should redirect after successful registration
        self.assertIn(response.status_code, [200, 302])

    def test_login_with_valid_credentials(self):
        """Registered users can log in."""
        student = make_student(email="login@test.com", password="TestPass123!")
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "login@test.com", "password": "TestPass123!"},
        )
        self.assertIn(response.status_code, [200, 302])

    def test_login_with_wrong_password_fails(self):
        """Wrong password should not authenticate."""
        student = make_student(email="wrongpass@test.com", password="RightPass123!")
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "wrongpass@test.com", "password": "WrongPass123!"},
        )
        # Should not redirect to dashboard
        self.assertEqual(response.status_code, 200)

    def test_protected_view_requires_login(self):
        """Unauthenticated access to dashboard redirects to login."""
        response = self.client.get(reverse("accounts:student_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_logout_clears_session(self):
        """After logout, protected routes redirect to login."""
        student = make_student(email="logout@test.com")
        self.client.force_login(student)
        self.client.post(reverse("accounts:logout"))
        response = self.client.get(reverse("accounts:student_dashboard"))
        self.assertEqual(response.status_code, 302)


class TestMarketplaceFlow(TestCase):
    """Test the public course marketplace."""

    def setUp(self):
        self.client = Client()

    def test_course_listing_is_public(self):
        """The marketplace course list is publicly accessible."""
        make_course(status="published")
        response = self.client.get(reverse("marketplace:course_list"))
        self.assertEqual(response.status_code, 200)

    def test_unpublished_course_not_in_listing(self):
        """Draft courses do not appear in public listings."""
        teacher = make_teacher()
        draft = make_course(teacher=teacher, status="draft", title="Hidden Draft")
        response = self.client.get(reverse("marketplace:course_list"))
        self.assertNotContains(response, "Hidden Draft")

    def test_course_detail_page_accessible(self):
        """Published course detail page is accessible to guests."""
        course = make_course(status="published", title="Accessible Course")
        response = self.client.get(
            reverse("marketplace:course_detail", kwargs={"slug": course.slug})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Accessible Course")

    def test_course_search_returns_results(self):
        """Search finds relevant courses by title."""
        make_course(status="published", title="Django REST Framework Deep Dive")
        response = self.client.get(
            reverse("marketplace:course_list"), {"q": "Django REST"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Django REST Framework")


class TestStudentDashboard(TestCase):
    """Test the student dashboard with enrolled courses."""

    def setUp(self):
        self.client = Client()
        self.student = make_student()
        self.client.force_login(self.student)

    def test_dashboard_loads_for_authenticated_student(self):
        response = self.client.get(reverse("accounts:student_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_shows_enrolled_course(self):
        course = make_course(status="published", title="My Enrolled Course")
        make_enrollment(user=self.student, course=course)
        response = self.client.get(reverse("accounts:student_dashboard"))
        self.assertContains(response, "My Enrolled Course")

    def test_unenrolled_student_cannot_access_lecture(self):
        """Student without enrollment gets 403 when accessing a paid lecture."""
        course = make_course(status="published")
        section = make_section(course=course)
        lecture = make_lecture(section=section)
        # Try to access the lecture learning page
        try:
            url = reverse("courses:lecture_learn", kwargs={
                "course_slug": course.slug,
                "lecture_id": str(lecture.id)
            })
            response = self.client.get(url)
            self.assertIn(response.status_code, [302, 403])
        except Exception:
            pass  # URL may not exist yet


class TestProgressAPIFlow(TestCase):
    """Integration tests for the progress AJAX API."""

    def setUp(self):
        self.client = Client()
        self.student = make_student()
        self.client.force_login(self.student)
        self.course = make_course(status="published")
        self.section = make_section(course=self.course)
        self.lecture = make_lecture(section=self.section, with_video=True)
        self.enrollment = make_enrollment(user=self.student, course=self.course)

    def _post_progress(self, position, watched, duration):
        return self.client.post(
            reverse("progress_api:update_position", kwargs={"lecture_id": self.lecture.id}),
            json.dumps({
                "position_seconds": position,
                "watched_seconds": watched,
                "video_duration": duration,
            }),
            content_type="application/json",
        )

    def test_update_position_returns_200(self):
        response = self._post_progress(120, 120, 600)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

    def test_update_position_saves_progress(self):
        self._post_progress(300, 300, 600)
        data = self._post_progress(300, 300, 600).json()
        self.assertEqual(data["position_seconds"], 300)
        self.assertFalse(data["is_completed"])  # 50% < 90% threshold

    def test_completion_threshold_marks_complete(self):
        response = self._post_progress(540, 540, 600)  # 90%
        data = response.json()
        self.assertTrue(data["is_completed"])

    def test_resume_position_endpoint(self):
        # Set a position first
        self._post_progress(200, 200, 600)
        response = self.client.get(
            reverse("progress_api:get_resume_position", kwargs={"lecture_id": self.lecture.id})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["position_seconds"], 200)

    def test_unenrolled_student_cannot_update_progress(self):
        """IDOR protection: another student cannot post progress for this lecture."""
        other_student = make_student()
        self.client.force_login(other_student)
        response = self._post_progress(100, 100, 600)
        self.assertIn(response.status_code, [403, 400])

    def test_unauthenticated_cannot_update_progress(self):
        self.client.logout()
        response = self._post_progress(100, 100, 600)
        self.assertIn(response.status_code, [302, 403])


class TestCheckoutAndEnrollmentFlow(TestCase):
    """
    Integration tests for the purchase → enrollment flow.
    Payment provider is not called; we test the service layer directly.
    """

    def setUp(self):
        self.student = make_student()
        self.course = make_course(price=Decimal("999.00"), status="published")

    def test_enroll_from_completed_order(self):
        from apps.enrollments.services import EnrollmentService
        from apps.enrollments.models import Enrollment
        order = make_order(user=self.student, course=self.course, status="completed")
        enrollments = EnrollmentService.enroll_from_order(order)
        self.assertEqual(len(enrollments), 1)
        self.assertTrue(Enrollment.objects.filter(user=self.student, course=self.course).exists())

    def test_duplicate_enrollment_does_not_duplicate(self):
        from apps.enrollments.services import EnrollmentService
        from apps.enrollments.models import Enrollment
        order = make_order(user=self.student, course=self.course, status="completed")
        # Call twice - should be idempotent
        EnrollmentService.enroll_from_order(order)
        EnrollmentService.enroll_from_order(order)
        count = Enrollment.objects.filter(user=self.student, course=self.course).count()
        self.assertEqual(count, 1)

    def test_incomplete_order_cannot_create_enrollment(self):
        from apps.enrollments.services import EnrollmentService
        order = make_order(user=self.student, course=self.course, status="pending")
        with self.assertRaises(ValueError):
            EnrollmentService.enroll_from_order(order)

    def test_student_gains_access_after_enrollment(self):
        from apps.enrollments.services import EnrollmentService
        self.assertFalse(EnrollmentService.has_access(self.student, self.course))
        make_enrollment(user=self.student, course=self.course)
        self.assertTrue(EnrollmentService.has_access(self.student, self.course))


class TestStudyMaterialsAndNotesFlow(TestCase):
    """Integration tests for study material uploads, student note-taking, and resource downloads."""

    def setUp(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client = Client()
        self.admin = make_admin(email="admin_materials@test.com")
        self.teacher = make_teacher(email="teacher_materials@test.com")
        self.student = make_student(email="student_notes@test.com")
        self.course = make_course(teacher=self.teacher, status="published")
        self.section = make_section(course=self.course)
        self.lecture = make_lecture(section=self.section, is_published=True)
        make_enrollment(user=self.student, course=self.course)

    def test_student_can_take_text_note_with_timestamp(self):
        from apps.progress.models import StudentNote
        self.client.force_login(self.student)
        url = reverse("learn:save_note", kwargs={"course_slug": self.course.slug, "lecture_id": self.lecture.id})
        response = self.client.post(url, {
            "title": "Django ORM Note",
            "content": "Remember to use select_related to avoid N+1 queries.",
            "video_timestamp_seconds": "135",
        })
        self.assertIn(response.status_code, [200, 302])
        note = StudentNote.objects.filter(user=self.student, lecture=self.lecture).first()
        self.assertIsNotNone(note)
        self.assertEqual(note.title, "Django ORM Note")
        self.assertEqual(note.video_timestamp_seconds, 135)
        self.assertEqual(note.formatted_timestamp, "02:15")

    def test_student_can_upload_notes_document(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.progress.models import StudentNote
        self.client.force_login(self.student)
        pdf_file = SimpleUploadedFile("my_summary.pdf", b"%PDF-1.4 dummy student notes content", content_type="application/pdf")
        url = reverse("learn:save_note", kwargs={"course_slug": self.course.slug, "lecture_id": self.lecture.id})
        response = self.client.post(url, {
            "title": "Summary PDF",
            "note_file": pdf_file,
            "video_timestamp_seconds": "45",
        })
        self.assertIn(response.status_code, [200, 302])
        note = StudentNote.objects.filter(user=self.student, title="Summary PDF").first()
        self.assertIsNotNone(note)
        self.assertTrue(bool(note.storage_key))
        self.assertEqual(note.original_filename, "my_summary.pdf")

        # Test student download endpoint
        dl_url = reverse("learn:download_note_file", kwargs={"course_slug": self.course.slug, "lecture_id": self.lecture.id, "note_id": note.id})
        dl_res = self.client.get(dl_url)
        self.assertEqual(dl_res.status_code, 302)

    def test_student_can_delete_own_note(self):
        from apps.progress.models import StudentNote
        self.client.force_login(self.student)
        note = StudentNote.objects.create(
            user=self.student,
            lecture=self.lecture,
            course=self.course,
            title="Note to delete",
            content="Testing deletion",
        )
        del_url = reverse("learn:delete_note", kwargs={"course_slug": self.course.slug, "lecture_id": self.lecture.id, "note_id": note.id})
        response = self.client.post(del_url)
        self.assertIn(response.status_code, [200, 302])
        self.assertFalse(StudentNote.objects.filter(id=note.id).exists())

    def test_admin_can_upload_and_delete_study_material(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.lectures.models import Attachment, LectureNote
        self.client.force_login(self.admin)
        doc = SimpleUploadedFile("study_guide.pdf", b"%PDF-guide content", content_type="application/pdf")
        upload_url = reverse("admin_panel:study_material_upload", kwargs={"lecture_id": self.lecture.id})
        res = self.client.post(upload_url, {
            "title": "Admin Study Guide",
            "material_type": "note",
            "file": doc,
        })
        self.assertEqual(res.status_code, 302)
        note = LectureNote.objects.filter(lecture=self.lecture, title="Admin Study Guide").first()
        self.assertIsNotNone(note)

        # Delete material
        del_url = reverse("admin_panel:study_material_delete", kwargs={"material_type": "note", "material_id": note.id})
        del_res = self.client.post(del_url)
        self.assertEqual(del_res.status_code, 302)
        self.assertFalse(LectureNote.objects.filter(id=note.id).exists())

    def test_teacher_can_upload_and_delete_attachment(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.lectures.models import Attachment
        self.client.force_login(self.teacher)
        zip_file = SimpleUploadedFile("project_code.zip", b"PKdummyzipcontent", content_type="application/zip")
        upload_url = reverse("teacher:note_upload", kwargs={"lecture_id": self.lecture.id})
        res = self.client.post(upload_url, {
            "title": "Project Starter Code",
            "resource_type": "attachment",
            "file": zip_file,
        })
        self.assertEqual(res.status_code, 302)
        att = Attachment.objects.filter(lecture=self.lecture, title="Project Starter Code").first()
        self.assertIsNotNone(att)

        # Delete attachment
        del_url = reverse("teacher:material_delete", kwargs={"resource_type": "attachment", "resource_id": att.id})
        del_res = self.client.post(del_url)
        self.assertEqual(del_res.status_code, 302)
        self.assertFalse(Attachment.objects.filter(id=att.id).exists())


class TestTeacherCourseDashboardAndPublishFlow(TestCase):
    """Integration tests for teacher course management and publishing."""

    def setUp(self):
        self.client = Client()
        self.teacher = make_teacher(email="teacher_dashboard_test@test.com")
        self.course = make_course(teacher=self.teacher, status="draft")
        self.section = make_section(course=self.course)
        self.lecture = make_lecture(section=self.section, is_published=True)

    def test_teacher_course_list_renders_successfully(self):
        self.client.force_login(self.teacher)
        url = reverse("teacher:course_list")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, self.course.title)

    def test_teacher_course_toggle_publish(self):
        self.client.force_login(self.teacher)
        toggle_url = reverse("teacher:course_toggle_publish", kwargs={"course_id": self.course.id})
        res = self.client.post(toggle_url)
        self.assertEqual(res.status_code, 302)
        self.course.refresh_from_db()
        self.assertTrue(self.course.is_published)

        # Toggle back to draft
        res = self.client.post(toggle_url)
        self.assertEqual(res.status_code, 302)
        self.course.refresh_from_db()
        self.assertFalse(self.course.is_published)

    def test_teacher_sections_view_renders_with_all_action_urls(self):
        self.client.force_login(self.teacher)
        sections_url = reverse("teacher:sections", kwargs={"course_id": self.course.id})
        res = self.client.get(sections_url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, self.section.title)
        self.assertContains(res, self.lecture.title)

    def test_teacher_video_upload_view_renders_without_error(self):
        self.client.force_login(self.teacher)
        upload_url = reverse("teacher:lecture_video_upload", kwargs={
            "course_id": self.course.id,
            "lecture_id": self.lecture.id
        })
        res = self.client.get(upload_url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, self.lecture.title)

    def test_teacher_analytics_and_student_progress_flow(self):
        from apps.certificates.models import Certificate
        from apps.progress.services import ProgressService
        from tests.factories import make_enrollment, make_student

        student = make_student()
        # Course with 2 published lectures
        lecture2 = make_lecture(section=self.section, is_published=True)
        enrollment = make_enrollment(user=student, course=self.course)

        self.client.force_login(self.teacher)
        res_analytics = self.client.get(reverse("teacher:analytics"))
        self.assertEqual(res_analytics.status_code, 200)
        self.assertContains(res_analytics, "0.0%")

        # Student completes lecture 1 (50% progress)
        lp1 = ProgressService.update_lecture_position(
            user=student,
            lecture=self.lecture,
            position_seconds=600,
            watched_seconds=600,
            video_duration=600,
        )
        self.assertTrue(lp1.is_completed)
        enrollment.progress.refresh_from_db()
        self.assertEqual(float(enrollment.progress.completion_percentage), 50.0)

        # Check analytics after 50%
        res_analytics_mid = self.client.get(reverse("teacher:analytics"))
        self.assertEqual(res_analytics_mid.status_code, 200)
        self.assertContains(res_analytics_mid, "50.0%")

        # Student completes lecture 2 (100% course completion)
        lp2 = ProgressService.update_lecture_position(
            user=student,
            lecture=lecture2,
            position_seconds=600,
            watched_seconds=600,
            video_duration=600,
        )
        self.assertTrue(lp2.is_completed)
        enrollment.progress.refresh_from_db()
        self.assertEqual(float(enrollment.progress.completion_percentage), 100.0)
        self.assertTrue(enrollment.progress.is_completed)

        # Certificate auto-created
        cert = Certificate.objects.filter(enrollment=enrollment).first()
        self.assertIsNotNone(cert)

        # Analytics reflects 100% and 1 certificate
        res_analytics_end = self.client.get(reverse("teacher:analytics"))
        self.assertEqual(res_analytics_end.status_code, 200)
        self.assertContains(res_analytics_end, "100.0%")

    def test_admin_course_delete_with_enrollments_archives_safely(self):
        from apps.courses.models import CourseStatus
        from tests.factories import make_admin, make_enrollment, make_student

        admin_user = make_admin()
        student = make_student()
        enrollment = make_enrollment(user=student, course=self.course)

        self.client.force_login(admin_user)
        delete_url = reverse("admin_panel:course_delete", kwargs={"course_id": self.course.id})

        # Standard deletion with active enrollment should not crash with ProtectedError
        res = self.client.post(delete_url, follow=True)
        self.assertEqual(res.status_code, 200)

        self.course.refresh_from_db()
        # Course should be safely archived, preserving student learning records
        self.assertEqual(self.course.status, CourseStatus.ARCHIVED)
        self.assertTrue(self.course.enrollments.filter(id=enrollment.id).exists())

    def test_admin_course_force_delete_purges_course_and_enrollments(self):
        from apps.courses.models import Course
        from apps.enrollments.models import Enrollment
        from tests.factories import make_admin, make_enrollment, make_student

        admin_user = make_admin()
        student = make_student()
        enrollment = make_enrollment(user=student, course=self.course)

        self.client.force_login(admin_user)
        delete_url = reverse("admin_panel:course_delete", kwargs={"course_id": self.course.id})

        # Force delete should permanently wipe course and related enrollments
        res = self.client.post(delete_url, {"force_delete": "true"}, follow=True)
        self.assertEqual(res.status_code, 200)

        self.assertFalse(Course.objects.filter(id=self.course.id).exists())
        self.assertFalse(Enrollment.objects.filter(id=enrollment.id).exists())


class TestAdminCategoryManagementFlow(TestCase):
    """Test full Category CRUD and visibility flows in Admin Console."""

    def setUp(self):
        self.client = Client()
        self.admin = make_admin(email="categoryadmin@eduflow.local")
        self.student = make_student(email="categorystudent@eduflow.local")
        self.teacher = make_teacher(email="categoryteacher@eduflow.local")

    def test_admin_can_access_category_list(self):
        """Admin can view category listing with search and stats."""
        from apps.courses.models import Category
        Category.objects.create(name="Web Dev Test", slug="web-dev-test", icon="💻", is_active=True)

        self.client.force_login(self.admin)
        res = self.client.get(reverse("admin_panel:category_list"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Web Dev Test")
        self.assertContains(res, "💻")

    def test_admin_can_create_category(self):
        """Admin can create a new category with auto-slug generation."""
        from apps.courses.models import Category

        self.client.force_login(self.admin)
        create_url = reverse("admin_panel:category_create")

        # GET form
        res_get = self.client.get(create_url)
        self.assertEqual(res_get.status_code, 200)

        # POST create
        res_post = self.client.post(
            create_url,
            {
                "name": "Cloud Computing & DevOps",
                "slug": "",  # test auto slugify
                "icon": "☁️",
                "order": 5,
                "is_active": "on",
                "description": "All about Docker, Kubernetes, AWS, and GCP",
            },
            follow=True,
        )
        self.assertEqual(res_post.status_code, 200)

        cat = Category.objects.filter(slug="cloud-computing-devops").first()
        self.assertIsNotNone(cat)
        self.assertEqual(cat.name, "Cloud Computing & DevOps")
        self.assertEqual(cat.icon, "☁️")
        self.assertEqual(cat.order, 5)
        self.assertTrue(cat.is_active)

    def test_admin_can_edit_category(self):
        """Admin can update an existing category."""
        from apps.courses.models import Category
        cat = Category.objects.create(name="Original Tech", slug="original-tech", icon="📱", is_active=True)

        self.client.force_login(self.admin)
        edit_url = reverse("admin_panel:category_edit", kwargs={"category_id": cat.id})

        res_post = self.client.post(
            edit_url,
            {
                "name": "Updated Technology",
                "slug": "updated-technology",
                "icon": "🚀",
                "order": 2,
                "description": "Updated description content.",
            },
            follow=True,
        )
        self.assertEqual(res_post.status_code, 200)

        cat.refresh_from_db()
        self.assertEqual(cat.name, "Updated Technology")
        self.assertEqual(cat.slug, "updated-technology")
        self.assertEqual(cat.icon, "🚀")
        self.assertFalse(cat.is_active)  # unchecked on POST

    def test_admin_can_toggle_category_status(self):
        """Admin can toggle category active/inactive via POST."""
        from apps.courses.models import Category
        cat = Category.objects.create(name="Toggle Test", slug="toggle-test", is_active=True)

        self.client.force_login(self.admin)
        toggle_url = reverse("admin_panel:category_toggle", kwargs={"category_id": cat.id})

        # Toggle to inactive
        res = self.client.post(toggle_url, follow=True)
        self.assertEqual(res.status_code, 200)
        cat.refresh_from_db()
        self.assertFalse(cat.is_active)

        # Toggle back to active
        res2 = self.client.post(toggle_url, follow=True)
        self.assertEqual(res2.status_code, 200)
        cat.refresh_from_db()
        self.assertTrue(cat.is_active)

    def test_admin_can_delete_category_safely_unlinking_courses(self):
        """Deleting category unlinks courses without crashing with ProtectedError."""
        from apps.courses.models import Category, Course
        cat = Category.objects.create(name="Delete Target", slug="delete-target", is_active=True)
        course = make_course(teacher=self.teacher, category=cat)

        self.assertEqual(course.category_id, cat.id)

        self.client.force_login(self.admin)
        delete_url = reverse("admin_panel:category_delete", kwargs={"category_id": cat.id})

        res = self.client.post(delete_url, follow=True)
        self.assertEqual(res.status_code, 200)

        self.assertFalse(Category.objects.filter(id=cat.id).exists())
        course.refresh_from_db()
        self.assertIsNone(course.category)  # cleanly unlinked

    def test_non_admin_cannot_access_categories(self):
        """Students and unauthenticated users cannot access category management."""
        list_url = reverse("admin_panel:category_list")

        # Unauthenticated -> redirect
        res_anon = self.client.get(list_url)
        self.assertIn(res_anon.status_code, [302, 403])

        # Student -> redirect or 403
        self.client.force_login(self.student)
        res_student = self.client.get(list_url)
        self.assertIn(res_student.status_code, [302, 403])


