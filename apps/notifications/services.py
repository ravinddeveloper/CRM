"""Application services for in-app notifications."""
import logging

from apps.courses.models import Course
from apps.enrollments.models import Enrollment
from infrastructure.database.exceptions import ApplicationValidationError
from infrastructure.database.factory import get_notification_repository

from .models import NotificationType

logger = logging.getLogger("apps.notifications")


class NotificationService:
    """Owns notification rules and delegates persistence to a repository."""

    @staticmethod
    def notify(user, notification_type: str, title: str, message: str, action_url: str = ""):
        if notification_type not in NotificationType.values:
            raise ApplicationValidationError("Choose a supported notification type.")
        if not str(title).strip() or len(title) > 255:
            raise ApplicationValidationError("Notification title is required and cannot exceed 255 characters.")
        if len(message) > 10_000:
            raise ApplicationValidationError("Notification message cannot exceed 10,000 characters.")
        if len(action_url) > 200:
            raise ApplicationValidationError("Notification action URL cannot exceed 200 characters.")
        return get_notification_repository().create(
            user_id=str(user.id), notification_type=notification_type,
            title=title.strip(), message=message, action_url=action_url,
        )

    @staticmethod
    def list_for_user(user_id: str, *, limit: int, offset: int):
        return get_notification_repository().list_for_user(user_id=str(user_id), limit=limit, offset=offset)

    @staticmethod
    def mark_read(notification_id: str, user_id: str):
        return get_notification_repository().mark_read(
            notification_id=str(notification_id), user_id=str(user_id)
        )

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
    def notify_purchase(user, order) -> None:
        NotificationService.notify(
            user=user,
            notification_type=NotificationType.PURCHASE,
            title="Purchase Confirmed!",
            message=f"Your order #{order.order_number} has been confirmed.",
            action_url=f"/orders/{order.id}/",
        )

    @staticmethod
    def notify_new_lecture(course: Course, lecture) -> None:
        """Notify enrolled students of a new lecture."""
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
