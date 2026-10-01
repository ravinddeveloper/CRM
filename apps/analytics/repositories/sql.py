"""SQL adapter for course page view events."""
from django.db import DatabaseError, transaction
from django.db.models import F

from apps.analytics.models import CourseView
from apps.courses.models import Course
from infrastructure.database.exceptions import DatabaseConnectionError

from .base import CourseViewRecord


class SQLCourseViewRepository:
    """Stores analytics events through the existing relational model."""

    def record_view(self, *, course_id, user_id, ip_address, session_key):
        try:
            with transaction.atomic():
                view = CourseView.objects.create(
                    course_id=course_id,
                    user_id=user_id,
                    ip_address=ip_address,
                    session_key=session_key,
                )
                Course.objects.filter(pk=course_id).update(total_views=F("total_views") + 1)
            return CourseViewRecord(
                id=str(view.id), course_id=str(view.course_id), user_id=str(view.user_id) if view.user_id else None,
                ip_address=view.ip_address, session_key=view.session_key, created_at=view.created_at,
            )
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not record the course view.") from exc

    def get_total_views(self, *, course_id):
        try:
            return Course.objects.values_list("total_views", flat=True).get(pk=course_id)
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not read the course view count.") from exc
