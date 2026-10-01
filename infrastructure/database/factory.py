"""Central selector for application repository implementations."""
from functools import lru_cache

from apps.accounts.repositories.base import AccountRepository
from apps.accounts.repositories.sql import SQLAccountRepository
from apps.analytics.repositories.base import CourseViewRepository
from apps.analytics.repositories.sql import SQLCourseViewRepository
from apps.notifications.repositories.base import NotificationRepository
from apps.notifications.repositories.sql import SQLNotificationRepository
from apps.enrollments.repositories.base import EnrollmentRepository
from apps.enrollments.repositories.sql import SQLEnrollmentRepository

from .config import DatabaseEngine, get_database_engine


def get_account_repository(engine: str | DatabaseEngine | None = None) -> AccountRepository:
    """Build the account adapter for the requested configured engine."""
    return _get_account_repository(get_database_engine(engine))


@lru_cache(maxsize=2)
def _get_account_repository(selected: DatabaseEngine) -> AccountRepository:
    if selected is DatabaseEngine.SQL:
        return SQLAccountRepository()
    if selected is DatabaseEngine.MONGODB:
        from apps.accounts.repositories.mongo import MongoAccountRepository

        return MongoAccountRepository()
    raise ValueError(f"No account repository is registered for {selected!r}.")


def get_course_view_repository(engine: str | DatabaseEngine | None = None) -> CourseViewRepository:
    """Build the analytics-event adapter for the requested configured engine."""
    return _get_course_view_repository(get_database_engine(engine))


@lru_cache(maxsize=2)
def _get_course_view_repository(selected: DatabaseEngine) -> CourseViewRepository:
    if selected is DatabaseEngine.SQL:
        return SQLCourseViewRepository()
    if selected is DatabaseEngine.MONGODB:
        from apps.analytics.repositories.mongo import MongoCourseViewRepository

        return MongoCourseViewRepository()
    raise ValueError(f"No course-view repository is registered for {selected!r}.")


def get_notification_repository(engine: str | DatabaseEngine | None = None) -> NotificationRepository:
    """Build the notification adapter for the requested configured engine."""
    return _get_notification_repository(get_database_engine(engine))


@lru_cache(maxsize=2)
def _get_notification_repository(selected: DatabaseEngine) -> NotificationRepository:
    if selected is DatabaseEngine.SQL:
        return SQLNotificationRepository()
    if selected is DatabaseEngine.MONGODB:
        from apps.notifications.repositories.mongo import MongoNotificationRepository

        return MongoNotificationRepository()
    raise ValueError(f"No notification repository is registered for {selected!r}.")


def get_enrollment_repository(engine: str | DatabaseEngine | None = None) -> EnrollmentRepository:
    """Build the student enrollment-listing adapter for the selected engine."""
    return _get_enrollment_repository(get_database_engine(engine))


@lru_cache(maxsize=2)
def _get_enrollment_repository(selected: DatabaseEngine) -> EnrollmentRepository:
    if selected is DatabaseEngine.SQL:
        return SQLEnrollmentRepository()
    if selected is DatabaseEngine.MONGODB:
        from apps.enrollments.repositories.mongo import MongoEnrollmentRepository

        return MongoEnrollmentRepository()
    raise ValueError(f"No enrollment repository is registered for {selected!r}.")
