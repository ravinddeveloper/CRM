"""Enrollment service - creates and manages course enrollments."""
import logging

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.courses.models import Course
from apps.orders.models import Order

from .models import Enrollment, EnrollmentStatus

User = get_user_model()
logger = logging.getLogger("apps.enrollments")


class EnrollmentService:
    """Handles enrollment creation and access checks."""

    @staticmethod
    @transaction.atomic
    def enroll_from_order(order: Order) -> list:
        """Create enrollments for all courses in a completed order."""
        if not order.is_completed:
            raise ValueError(f"Order {order.order_number} is not completed.")

        enrollments = []
        for item in order.items.select_related("course").all():
            enrollment, created = Enrollment.objects.get_or_create(
                user=order.user,
                course=item.course,
                defaults={
                    "order": order,
                    "status": EnrollmentStatus.ACTIVE,
                    "access_type": "lifetime",
                },
            )
            if created:
                # Initialize course progress
                from apps.progress.models import CourseProgress
                progress, _ = CourseProgress.objects.get_or_create(enrollment=enrollment)

                # Update course enrollment count
                item.course.enrollment_count = item.course.enrollments.filter(
                    status=EnrollmentStatus.ACTIVE
                ).count()
                item.course.save(update_fields=["enrollment_count"])

                # Notify admin/teacher
                from apps.notifications.services import NotificationService
                NotificationService.notify_enrollment(enrollment)

                logger.info(
                    "Enrollment created: user=%s course=%s order=%s",
                    order.user.email, item.course.title, order.order_number
                )
            else:
                logger.info(
                    "Enrollment already exists: user=%s course=%s",
                    order.user.email, item.course.title
                )
            enrollments.append(enrollment)

        return enrollments

    @staticmethod
    def enroll_free(user: User, course: Course) -> Enrollment:
        """Enroll a user in a free course without payment."""
        if not course.is_free and course.effective_price > 0:
            raise ValueError("Course is not free.")

        enrollment, created = Enrollment.objects.get_or_create(
            user=user,
            course=course,
            defaults={"status": EnrollmentStatus.ACTIVE},
        )
        if created:
            from apps.progress.models import CourseProgress
            CourseProgress.objects.get_or_create(enrollment=enrollment)
        return enrollment

    @staticmethod
    def has_access(user: User, course: Course) -> bool:
        """
        Check if a user has active access to a course.
        This is THE authoritative access check — used by all views.
        """
        if not user.is_authenticated:
            return False
        if user.is_admin or user.is_staff:
            return True
        if user.is_teacher and course.teacher_id == user.id:
            return True
        try:
            enrollment = Enrollment.objects.get(user=user, course=course)
            return enrollment.is_active
        except Enrollment.DoesNotExist:
            return False

    @staticmethod
    def get_enrollment(user: User, course: Course) -> Enrollment | None:
        """Get enrollment if it exists."""
        try:
            return Enrollment.objects.get(user=user, course=course)
        except Enrollment.DoesNotExist:
            return None
