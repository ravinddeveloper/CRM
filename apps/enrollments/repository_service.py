"""Backend-neutral enrollment listing with relational course-catalog hydration."""
from apps.courses.models import Course
from infrastructure.database.factory import get_enrollment_repository


def list_enrollments_for_user(*, user_id, limit, offset, repository=None):
    """Return enrollment records and catalog courses for the student API.

    Courses remain in Django's relational catalog during the staged migration;
    only enrollment rows use the selected repository at this stage.
    """
    repo = repository or get_enrollment_repository()
    count, records = repo.list_for_user(user_id=str(user_id), limit=limit, offset=offset)
    course_ids = {record.course_id for record in records}
    courses = Course.objects.filter(pk__in=course_ids).select_related("category", "teacher")
    course_by_id = {str(course.pk): course for course in courses}
    return count, [(record, course_by_id.get(record.course_id)) for record in records]
