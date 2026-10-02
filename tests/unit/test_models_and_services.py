"""
Unit tests: Models, Services, and business logic.
Tests are isolated and do not depend on HTTP layer.
"""
import pytest
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone

from tests.factories import (
    make_admin, make_teacher, make_student, make_course,
    make_section, make_lecture, make_enrollment, make_order,
)


# ──────────────────────────────────────────────────────────────────────────────
# User model tests
# ──────────────────────────────────────────────────────────────────────────────

class TestUserModel(TestCase):

    def test_create_student(self):
        student = make_student(email="student@example.com")
        self.assertEqual(student.role, "student")
        self.assertTrue(student.is_student)
        self.assertFalse(student.is_teacher)
        self.assertFalse(student.is_admin)

    def test_create_teacher(self):
        teacher = make_teacher()
        self.assertTrue(teacher.is_teacher)
        self.assertFalse(teacher.is_student)

    def test_create_admin(self):
        admin = make_admin()
        self.assertTrue(admin.is_admin)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_user_full_name(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.create_user(
            email="fn@test.com", password="pass", username="fn",
            first_name="John", last_name="Doe"
        )
        self.assertEqual(user.full_name, "John Doe")

    def test_user_full_name_fallback_email(self):
        student = make_student(email="nofullname@test.com")
        self.assertEqual(student.full_name, "nofullname@test.com")

    def test_suspend_user(self):
        student = make_student()
        student.suspend(reason="Policy violation")
        self.assertFalse(student.is_active)
        self.assertTrue(student.is_suspended)
        self.assertEqual(student.suspended_reason, "Policy violation")

    def test_activate_suspended_user(self):
        student = make_student()
        student.suspend()
        student.activate()
        self.assertTrue(student.is_active)
        self.assertFalse(student.is_suspended)

    def test_password_stored_as_hash(self):
        student = make_student(password="SecurePassword123!")
        self.assertNotEqual(student.password, "SecurePassword123!")
        self.assertTrue(student.check_password("SecurePassword123!"))


# ──────────────────────────────────────────────────────────────────────────────
# Course model tests
# ──────────────────────────────────────────────────────────────────────────────

class TestCourseModel(TestCase):

    def test_effective_price_uses_discount(self):
        course = make_course(price=Decimal("1000.00"))
        course.discount_price = Decimal("799.00")
        course.save()
        self.assertEqual(course.effective_price, Decimal("799.00"))

    def test_effective_price_uses_regular_when_no_discount(self):
        course = make_course(price=Decimal("999.00"))
        self.assertEqual(course.effective_price, Decimal("999.00"))

    def test_free_course_effective_price_is_zero(self):
        course = make_course(price=Decimal("999.00"))
        course.is_free = True
        course.save()
        self.assertEqual(course.effective_price, Decimal("0.00"))

    def test_discount_percentage(self):
        course = make_course(price=Decimal("1000.00"))
        course.discount_price = Decimal("800.00")
        course.save()
        self.assertEqual(course.discount_percentage, 20)

    def test_slug_auto_generated(self):
        course = make_course(title="My Python Course")
        self.assertIn("python", course.slug)

    def test_publish_sets_published_at(self):
        course = make_course(status="draft")
        course.publish()
        self.assertEqual(course.status, "published")
        self.assertIsNotNone(course.published_at)

    def test_is_published_property(self):
        course = make_course(status="published")
        self.assertTrue(course.is_published)
        course.status = "draft"
        course.save()
        self.assertFalse(course.is_published)


# ──────────────────────────────────────────────────────────────────────────────
# Enrollment model tests
# ──────────────────────────────────────────────────────────────────────────────

class TestEnrollmentModel(TestCase):

    def test_active_lifetime_enrollment(self):
        enrollment = make_enrollment()
        self.assertTrue(enrollment.is_active)

    def test_expired_enrollment_is_not_active(self):
        from apps.enrollments.models import Enrollment, EnrollmentStatus, AccessType
        student = make_student()
        course = make_course()
        enrollment = Enrollment.objects.create(
            user=student,
            course=course,
            status=EnrollmentStatus.ACTIVE,
            access_type=AccessType.FIXED_DURATION,
            expires_at=timezone.now() - timezone.timedelta(days=1),
        )
        self.assertFalse(enrollment.is_active)

    def test_revoked_enrollment_is_not_active(self):
        enrollment = make_enrollment()
        enrollment.revoke()
        self.assertFalse(enrollment.is_active)

    def test_duplicate_enrollment_raises(self):
        from django.db import IntegrityError
        student = make_student()
        course = make_course()
        make_enrollment(user=student, course=course)
        with self.assertRaises(IntegrityError):
            make_enrollment(user=student, course=course)


# ──────────────────────────────────────────────────────────────────────────────
# EnrollmentService tests
# ──────────────────────────────────────────────────────────────────────────────

class TestEnrollmentService(TestCase):

    def test_has_access_returns_false_for_unenrolled(self):
        from apps.enrollments.services import EnrollmentService
        student = make_student()
        course = make_course()
        self.assertFalse(EnrollmentService.has_access(student, course))

    def test_has_access_returns_true_for_enrolled(self):
        from apps.enrollments.services import EnrollmentService
        student = make_student()
        course = make_course()
        make_enrollment(user=student, course=course)
        self.assertTrue(EnrollmentService.has_access(student, course))

    def test_has_access_true_for_admin(self):
        from apps.enrollments.services import EnrollmentService
        admin = make_admin()
        course = make_course()
        self.assertTrue(EnrollmentService.has_access(admin, course))

    def test_has_access_true_for_course_teacher(self):
        from apps.enrollments.services import EnrollmentService
        teacher = make_teacher()
        course = make_course(teacher=teacher)
        self.assertTrue(EnrollmentService.has_access(teacher, course))

    def test_has_access_false_for_different_teacher(self):
        from apps.enrollments.services import EnrollmentService
        teacher1 = make_teacher()
        teacher2 = make_teacher()
        course = make_course(teacher=teacher1)
        self.assertFalse(EnrollmentService.has_access(teacher2, course))

    def test_enroll_free_course(self):
        from apps.enrollments.services import EnrollmentService
        student = make_student()
        course = make_course(price=Decimal("0.00"))
        course.is_free = True
        course.save()
        enrollment = EnrollmentService.enroll_free(user=student, course=course)
        self.assertEqual(enrollment.status, "active")

    def test_enroll_free_raises_for_paid_course(self):
        from apps.enrollments.services import EnrollmentService
        student = make_student()
        course = make_course(price=Decimal("999.00"))
        with self.assertRaises(ValueError):
            EnrollmentService.enroll_free(user=student, course=course)


# ──────────────────────────────────────────────────────────────────────────────
# LectureProgress / ProgressService tests
# ──────────────────────────────────────────────────────────────────────────────

class TestLectureProgress(TestCase):

    def setUp(self):
        self.student = make_student()
        self.course = make_course()
        self.section = make_section(course=self.course)
        self.lecture = make_lecture(section=self.section, with_video=True)
        self.enrollment = make_enrollment(user=self.student, course=self.course)

    def test_video_position_update_saves_position(self):
        from apps.progress.services import ProgressService
        lp = ProgressService.update_lecture_position(
            user=self.student,
            lecture=self.lecture,
            position_seconds=120,
            watched_seconds=120,
            video_duration=600,
        )
        self.assertEqual(lp.video_position_seconds, 120)
        self.assertFalse(lp.is_completed)  # 120/600 = 20%, below threshold

    def test_lecture_marked_complete_at_threshold(self):
        from apps.progress.services import ProgressService
        # Watch 90% of a 600s video = 540s
        lp = ProgressService.update_lecture_position(
            user=self.student,
            lecture=self.lecture,
            position_seconds=540,
            watched_seconds=540,
            video_duration=600,
        )
        self.assertTrue(lp.is_completed)
        self.assertIsNotNone(lp.completed_at)

    def test_course_completion_recalculates_correctly(self):
        from apps.progress.services import ProgressService
        from apps.progress.models import CourseProgress
        # Mark lecture complete
        ProgressService.update_lecture_position(
            user=self.student,
            lecture=self.lecture,
            position_seconds=600,
            watched_seconds=600,
            video_duration=600,
        )
        cp = CourseProgress.objects.get(enrollment=self.enrollment)
        # 1/1 lecture completed = 100%
        self.assertEqual(cp.completion_percentage, Decimal("100.00"))
        self.assertTrue(cp.is_completed)

    def test_position_never_goes_backwards(self):
        from apps.progress.services import ProgressService
        # First update
        ProgressService.update_lecture_position(
            user=self.student, lecture=self.lecture,
            position_seconds=300, watched_seconds=300, video_duration=600,
        )
        # Try to go back (e.g. player reset)
        lp = ProgressService.update_lecture_position(
            user=self.student, lecture=self.lecture,
            position_seconds=10, watched_seconds=10, video_duration=600,
        )
        # Position should be clamped to maximum seen
        self.assertGreaterEqual(lp.video_position_seconds, 300)

    def test_unenrolled_user_cannot_update_progress(self):
        from apps.progress.services import ProgressService
        other_student = make_student()
        with self.assertRaises(PermissionError):
            ProgressService.update_lecture_position(
                user=other_student,
                lecture=self.lecture,
                position_seconds=100,
                watched_seconds=100,
                video_duration=600,
            )


# ──────────────────────────────────────────────────────────────────────────────
# Order model tests
# ──────────────────────────────────────────────────────────────────────────────

class TestOrderModel(TestCase):

    def test_order_total_matches_items(self):
        from apps.orders.models import Order, OrderStatus
        student = make_student()
        course = make_course(price=Decimal("999.00"))
        order = make_order(user=student, course=course, status="completed")
        self.assertEqual(order.total, Decimal("999.00"))

    def test_order_is_completed(self):
        from apps.orders.models import OrderStatus
        order = make_order(status="completed")
        self.assertTrue(order.is_completed)

    def test_order_number_is_set(self):
        order = make_order()
        self.assertIsNotNone(order.order_number)
        self.assertTrue(len(order.order_number) > 0)


# ──────────────────────────────────────────────────────────────────────────────
# Coupon model tests
# ──────────────────────────────────────────────────────────────────────────────

class TestCouponCalculations(TestCase):

    def _make_coupon(self, **kwargs):
        from apps.coupons.models import Coupon, DiscountType
        return Coupon.objects.create(
            code=f"TEST{kwargs.get('suffix', '10')}",
            discount_type=kwargs.get("discount_type", DiscountType.PERCENTAGE),
            discount_value=kwargs.get("discount_value", Decimal("10.00")),
            is_active=True,
            valid_from=timezone.now() - timezone.timedelta(days=1),
            valid_until=timezone.now() + timezone.timedelta(days=30),
            max_uses=100,
        )

    def test_percentage_coupon_calculation(self):
        from apps.coupons.models import DiscountType
        coupon = self._make_coupon(discount_type=DiscountType.PERCENTAGE, discount_value=Decimal("20"))
        # 20% of 1000 = 200 discount
        discount = coupon.calculate_discount(Decimal("1000.00"))
        self.assertEqual(discount, Decimal("200.00"))

    def test_fixed_coupon_calculation(self):
        from apps.coupons.models import DiscountType
        coupon = self._make_coupon(
            suffix="FX",
            discount_type=DiscountType.FIXED,
            discount_value=Decimal("100.00"),
        )
        discount = coupon.calculate_discount(Decimal("1000.00"))
        self.assertEqual(discount, Decimal("100.00"))

    def test_coupon_discount_cannot_exceed_total(self):
        from apps.coupons.models import DiscountType
        coupon = self._make_coupon(
            suffix="BIG",
            discount_type=DiscountType.FIXED,
            discount_value=Decimal("2000.00"),  # more than total
        )
        discount = coupon.calculate_discount(Decimal("999.00"))
        self.assertLessEqual(discount, Decimal("999.00"))


# ──────────────────────────────────────────────────────────────────────────────
# Storage service tests
# ──────────────────────────────────────────────────────────────────────────────

class TestStorageService(TestCase):

    def test_get_presigned_url_returns_string(self):
        """StorageService.get_presigned_url should return a non-empty URL string."""
        from apps.storage.service import StorageService
        url = StorageService.get_presigned_url("test/file.mp4", expires_in=300)
        self.assertIsInstance(url, str)
        self.assertTrue(len(url) > 0)

    def test_storage_service_upload_exists_delete_cycle(self):
        """Test file upload, file_exists, get_file_size, and delete_file."""
        import io
        from apps.storage.service import StorageService

        key = "test_dir/sample_test_file.txt"
        content = b"Storage test data payload."
        file_obj = io.BytesIO(content)

        # Upload
        uploaded_key = StorageService.upload_file(key, file_obj, "text/plain")
        self.assertEqual(uploaded_key, key)

        # Exists
        self.assertTrue(StorageService.file_exists(key))

        # Size
        self.assertEqual(StorageService.get_file_size(key), len(content))

        # Delete
        StorageService.delete_file(key)
        self.assertFalse(StorageService.file_exists(key))

    def test_build_key(self):
        """Test build_key generates formatted unique path."""
        from apps.storage.service import StorageService
        key = StorageService.build_key("courses/videos", "sample.mp4")
        self.assertTrue(key.startswith("courses/videos/"))
        self.assertTrue(key.endswith(".mp4"))

    def test_safe_filename(self):
        """Test safe_filename sanitizes filenames and strips paths."""
        from apps.storage.service import safe_filename
        self.assertEqual(safe_filename("simple.txt"), "simple.txt")
        self.assertEqual(safe_filename("../../../etc/passwd.txt"), "passwd.txt")
        self.assertNotIn(" ", safe_filename("my file name (1).pdf"))

    def test_azure_module_exists_and_can_be_imported(self):
        """Ensure apps.storage.azure module exists and defines AzureBlobStorageService."""
        from apps.storage.azure import AzureBlobStorageService
        self.assertTrue(issubclass(AzureBlobStorageService, object))


# ──────────────────────────────────────────────────────────────────────────────
# Staff Shift & Work Hours Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestStaffShiftWorkHoursCalculation(TestCase):

    def setUp(self):
        from tests.factories import make_teacher
        self.employee = make_teacher()

    def test_shift_duration_properties_completed_shift(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.scheduling.models import StaffShift

        now = timezone.now()
        shift = StaffShift.objects.create(
            employee=self.employee,
            checked_in_at=now - timedelta(hours=2, minutes=30),
            checked_out_at=now,
        )
        self.assertFalse(shift.is_open)
        self.assertEqual(shift.duration_seconds, 2 * 3600 + 30 * 60)
        self.assertEqual(shift.duration_hours, 2.5)
        self.assertEqual(shift.formatted_duration, "2h 30m")

    def test_shift_duration_short_shift(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.scheduling.models import StaffShift

        now = timezone.now()
        shift = StaffShift.objects.create(
            employee=self.employee,
            checked_in_at=now - timedelta(seconds=45),
            checked_out_at=now,
        )
        self.assertEqual(shift.duration_seconds, 45)
        self.assertEqual(shift.formatted_duration, "45s")

    def test_shift_statistics_today_and_total(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.scheduling.models import StaffShift
        from apps.scheduling.services import get_shift_statistics

        now = timezone.now()

        # Shift 1: 3 hours ago today (duration 2 hours)
        StaffShift.objects.create(
            employee=self.employee,
            checked_in_at=now - timedelta(hours=3),
            checked_out_at=now - timedelta(hours=1),
        )

        # Shift 2: 3 days ago (duration 4 hours)
        past_employee = self.employee
        StaffShift.objects.create(
            employee=past_employee,
            checked_in_at=now - timedelta(days=3, hours=5),
            checked_out_at=now - timedelta(days=3, hours=1),
        )

        stats = get_shift_statistics()
        # Today: 2 hours (7200s)
        self.assertEqual(stats["today_hours"], 2.0)
        self.assertEqual(stats["formatted_today_hours"], "2h 00m")
        self.assertEqual(stats["today_shifts_count"], 1)

        # Total: 2h + 4h = 6 hours (21600s)
        self.assertEqual(stats["total_hours"], 6.0)
        self.assertEqual(stats["formatted_total_hours"], "6h 00m")
        self.assertEqual(stats["total_shifts_count"], 2)

    def test_admin_scheduling_view_includes_work_hours(self):
        from datetime import timedelta
        from django.urls import reverse
        from django.utils import timezone
        from apps.scheduling.models import StaffShift
        from tests.factories import make_admin

        admin_user = make_admin()
        now = timezone.now()
        StaffShift.objects.create(
            employee=self.employee,
            checked_in_at=now - timedelta(hours=1, minutes=45),
            checked_out_at=now,
        )

        self.client.force_login(admin_user)
        res = self.client.get(reverse("admin_panel:schedule_attendance"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Today's Work Hours")
        self.assertContains(res, "Total Work Hours")
        self.assertContains(res, "Work hours")
        self.assertContains(res, "1h 45m")

    def test_shift_statistics_individual_calculation(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.scheduling.models import StaffShift
        from apps.scheduling.services import get_shift_statistics
        from tests.factories import make_teacher

        emp1 = self.employee
        emp2 = make_teacher(email="instructor2@example.com")
        now = timezone.now()

        # emp1: 2 hours today
        StaffShift.objects.create(
            employee=emp1,
            checked_in_at=now - timedelta(hours=2),
            checked_out_at=now,
            check_in_ip="192.168.1.10",
        )

        # emp2: 3 hours today, 1 hour 3 days ago
        StaffShift.objects.create(
            employee=emp2,
            checked_in_at=now - timedelta(hours=3),
            checked_out_at=now,
            check_in_ip="192.168.1.20",
        )
        StaffShift.objects.create(
            employee=emp2,
            checked_in_at=now - timedelta(days=3, hours=2),
            checked_out_at=now - timedelta(days=3, hours=1),
            check_in_ip="192.168.1.20",
        )

        # 1. Total platform stats
        all_stats = get_shift_statistics()
        self.assertEqual(all_stats["today_hours"], 5.0)
        self.assertEqual(all_stats["total_hours"], 6.0)

        # 2. Individual stats breakdown
        indiv_stats = all_stats["individual_stats"]
        emp1_stat = next(item for item in indiv_stats if item["user_id"] == str(emp1.id))
        emp2_stat = next(item for item in indiv_stats if item["user_id"] == str(emp2.id))

        self.assertEqual(emp1_stat["today_hours"], 2.0)
        self.assertEqual(emp1_stat["total_hours"], 2.0)
        self.assertEqual(emp1_stat["last_ip"], "192.168.1.10")

        self.assertEqual(emp2_stat["today_hours"], 3.0)
        self.assertEqual(emp2_stat["total_hours"], 4.0)
        self.assertEqual(emp2_stat["last_ip"], "192.168.1.20")

        # 3. Filter specifically by individual employee
        emp1_filtered = get_shift_statistics(employee=emp1)
        self.assertEqual(emp1_filtered["today_hours"], 2.0)
        self.assertEqual(emp1_filtered["total_hours"], 2.0)

        emp2_filtered = get_shift_statistics(employee=emp2)
        self.assertEqual(emp2_filtered["today_hours"], 3.0)
        self.assertEqual(emp2_filtered["total_hours"], 4.0)

    def test_user_login_records_shift_and_logout_clocks_out(self):
        from django.contrib.auth.signals import user_logged_in, user_logged_out
        from django.test import RequestFactory
        from apps.scheduling.models import StaffShift
        from tests.factories import make_teacher

        teacher = make_teacher(email="shift_tracker@example.com")
        factory = RequestFactory()

        # Simulate user login with IP
        request = factory.post("/accounts/login/")
        request.META["REMOTE_ADDR"] = "203.0.113.42"
        user_logged_in.send(sender=teacher.__class__, request=request, user=teacher)

        # Verify shift was automatically opened with login IP
        shift = StaffShift.objects.filter(employee=teacher, checked_out_at__isnull=True).first()
        self.assertIsNotNone(shift)
        self.assertEqual(shift.check_in_ip, "203.0.113.42")
        self.assertTrue(shift.is_open)

        # Simulate user logout with IP
        logout_request = factory.post("/accounts/logout/")
        logout_request.META["REMOTE_ADDR"] = "203.0.113.43"
        user_logged_out.send(sender=teacher.__class__, request=logout_request, user=teacher)

        # Verify shift was clocked out
        shift.refresh_from_db()
        self.assertFalse(shift.is_open)
        self.assertIsNotNone(shift.checked_out_at)
        self.assertEqual(shift.check_out_ip, "203.0.113.43")

    def test_admin_scheduling_view_with_individual_employee_filter(self):
        from datetime import timedelta
        from django.urls import reverse
        from django.utils import timezone
        from apps.scheduling.models import StaffShift
        from tests.factories import make_admin, make_teacher

        admin_user = make_admin()
        emp1 = self.employee
        emp2 = make_teacher(email="other_emp@example.com")
        now = timezone.now()

        StaffShift.objects.create(
            employee=emp1,
            checked_in_at=now - timedelta(hours=1),
            checked_out_at=now,
            check_in_ip="10.0.0.1",
        )
        StaffShift.objects.create(
            employee=emp2,
            checked_in_at=now - timedelta(hours=3),
            checked_out_at=now,
            check_in_ip="10.0.0.2",
        )

        self.client.force_login(admin_user)

        # Filter by emp1
        res = self.client.get(reverse("admin_panel:schedule_attendance") + f"?employee={emp1.id}")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Viewing Individual Hours")
        self.assertContains(res, "10.0.0.1")
        self.assertNotContains(res, "10.0.0.2")

    def test_scheduling_and_attendance_tab_separation(self):
        from datetime import timedelta
        from django.utils import timezone
        from django.urls import reverse
        from tests.factories import make_admin, make_course, make_student
        from apps.scheduling.models import Session, SessionBooking, SessionType

        admin_user = make_admin()
        student = make_student(email="tab_student@example.com")
        course = make_course(title="Scheduling Test Course")

        session = Session.objects.create(
            title="Separated Class Session",
            course=course,
            instructor=admin_user,
            session_type=SessionType.LIVE_ONLINE,
            starts_at=timezone.now() + timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=1, hours=1),
        )
        booking = SessionBooking.objects.create(
            session=session,
            member=student,
        )

        self.client.force_login(admin_user)

        # Tab: Schedule
        res_schedule = self.client.get(reverse("admin_panel:schedule_attendance") + "?tab=schedule")
        self.assertEqual(res_schedule.status_code, 200)
        self.assertContains(res_schedule, "Class & Session Schedule")
        self.assertContains(res_schedule, "Separated Class Session")
        self.assertNotContains(res_schedule, "All Booking Statuses")

        # Tab: Attendance
        res_attendance = self.client.get(reverse("admin_panel:schedule_attendance") + "?tab=attendance")
        self.assertEqual(res_attendance.status_code, 200)
        self.assertContains(res_attendance, "Member Attendance & Bookings")
        self.assertContains(res_attendance, "tab_student@example.com")
        self.assertNotContains(res_attendance, "Upcoming Sessions")

    def test_announcement_crud_and_student_visibility(self):
        from django.urls import reverse
        from tests.factories import make_admin, make_teacher, make_student, make_course
        from apps.notifications.models import Announcement, AnnouncementPriority
        from apps.enrollments.models import Enrollment

        admin_user = make_admin()
        teacher = make_teacher(email="ann_teacher@example.com")
        student = make_student(email="ann_student@example.com")
        course = make_course(title="React Masterclass", teacher=teacher)
        Enrollment.objects.create(user=student, course=course, status="active")

        # 1. Admin creates platform-wide announcement
        self.client.force_login(admin_user)
        res_create = self.client.post(reverse("admin_panel:announcement_create"), {
            "title": "Welcome to New Semester",
            "content": "All courses have been updated with 2026 modules.",
            "priority": AnnouncementPriority.IMPORTANT,
            "is_published": "on",
            "is_pinned": "on",
        })
        self.assertEqual(res_create.status_code, 302)
        self.assertTrue(Announcement.objects.filter(title="Welcome to New Semester").exists())

        # 2. Teacher creates course-specific announcement
        self.client.force_login(teacher)
        res_teacher_create = self.client.post(reverse("teacher:announcement_create"), {
            "title": "React Class Tomorrow",
            "content": "Please review lecture 4 beforehand.",
            "course": str(course.id),
            "priority": AnnouncementPriority.URGENT,
            "is_published": "on",
        })
        self.assertEqual(res_teacher_create.status_code, 302)
        self.assertTrue(Announcement.objects.filter(title="React Class Tomorrow", course=course).exists())

        # 3. Student can view announcements on public list & detail
        self.client.force_login(student)
        res_list = self.client.get(reverse("notifications:announcement_list"))
        self.assertEqual(res_list.status_code, 200)
        self.assertContains(res_list, "Welcome to New Semester")
        self.assertContains(res_list, "React Class Tomorrow")

        ann = Announcement.objects.get(title="Welcome to New Semester")
        res_detail = self.client.get(reverse("notifications:announcement_detail", kwargs={"announcement_id": ann.id}))
        self.assertEqual(res_detail.status_code, 200)
        self.assertContains(res_detail, "All courses have been updated with 2026 modules.")

        # 4. Student dashboard shows announcement banner
        res_dash = self.client.get(reverse("accounts:student_dashboard"))
        self.assertEqual(res_dash.status_code, 200)
        self.assertContains(res_dash, "Welcome to New Semester")

