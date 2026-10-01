"""Application service for recording analytics events."""
from infrastructure.database.factory import get_course_view_repository


class AnalyticsService:
    """Coordinates event writes without exposing storage-specific models."""

    @staticmethod
    def record_course_view(*, course_id, user_id=None, ip_address=None, session_key=""):
        return get_course_view_repository().record_view(
            course_id=str(course_id),
            user_id=str(user_id) if user_id else None,
            ip_address=ip_address,
            session_key=session_key,
        )
