"""SQL adapter for student enrollment listings."""
from django.db import DatabaseError

from apps.enrollments.models import Enrollment
from infrastructure.database.exceptions import DatabaseConnectionError

from .base import EnrollmentRecord


class SQLEnrollmentRepository:
    @staticmethod
    def _record(enrollment):
        return EnrollmentRecord(
            id=str(enrollment.pk), user_id=str(enrollment.user_id),
            course_id=str(enrollment.course_id), status=enrollment.status,
            access_type=enrollment.access_type, expires_at=enrollment.expires_at,
            created_at=enrollment.created_at,
        )

    def list_for_user(self, *, user_id, limit, offset):
        try:
            rows = Enrollment.objects.filter(user_id=user_id).order_by("-created_at", "-id")
            count = rows.count()
            return count, [self._record(row) for row in rows[offset:offset + limit]]
        except DatabaseError as exc:
            raise DatabaseConnectionError("The SQL database could not list enrollments.") from exc
