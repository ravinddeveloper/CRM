"""Notification service."""
import logging

from django.contrib.auth import get_user_model

from apps.courses.models import Course
from apps.enrollments.models import Enrollment

from .models import Notification, NotificationType

User = get_user_model()
logger = logging.getLogger("apps.notifications")


class NotificationService:
    """Creates in-app notifications."""

    @staticmethod
    def notify(user: User, notification_type: str, title: str, message: str, action_url: str = "") -> Notification:
        n = Notification.objects.create(
            user=user,
            notification_type=notification_type,
            title=title,
            message=message,
            action_url=action_url,
        )
        return n

    @staticmethod
    def notify_enrollment(enrollment: Enrollment) -> None:
        NotificationService.notify(
            user=enrollment.user,
            notification_type=NotificationType.ENROLLMENT,
            title=f"You're now enrolled in {enrollment.course.title}!",
            message=f"Start learning {enrollment.course.title} anytime.",
            action_url=f"/learn/{enrollment.course.slug}/",
        )

    @staticmethod
    def notify_purchase(user: User, order) -> None:
        NotificationService.notify(
            user=user,
            notification_type=NotificationType.PURCHASE,
            title="Purchase Confirmed!",
            message=f"Your order #{order.order_number} has been confirmed.",
            action_url=f"/orders/{order.id}/",
        )

    @staticmethod
    def notify_new_lecture(course: Course, lecture) -> None:
        """Notify all enrolled students of a new lecture."""
        enrollments = course.enrollments.filter(status="active").select_related("user")
        for enrollment in enrollments:
            if enrollment.user.profile.notification_new_lecture:
                NotificationService.notify(
                    user=enrollment.user,
                    notification_type=NotificationType.NEW_LECTURE,
                    title=f"New lecture in {course.title}",
                    message=f"New lecture available: {lecture.title}",
                    action_url=f"/learn/{course.slug}/{lecture.id}/",
                )
