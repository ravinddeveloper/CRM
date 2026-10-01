"""SQL adapter for course page view events."""
from django.db import DatabaseError

from apps.analytics.models import CourseView
from infrastructure.database.exceptions import DatabaseConnectionError

from .base import CourseViewRecord


class SQLCourseViewRepository:
    """Stores analytics events through the existing relational model."""

    def record_view(self, *, course_id, user_id, ip_address, session_key):
        try:
            view = CourseView.objects.create(
                course_id=course_id,
                user_id=user_id,
                ip_address=ip_address,
                session_key=session_key,
            )
            return CourseViewRecord(
                id=str(view.id), course_id=str(view.course_id), user_id=str(view.user_id) if view.user_id else None,
                ip_address=view.ip_address, session_key=view.session_key, created_at=view.created_at,
            )
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not record the course view.") from exc
