"""Progress service - manages lecture/course progress calculations."""
import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.enrollments.services import EnrollmentService
from apps.lectures.models import Lecture
from apps.progress.models import CourseProgress, LectureProgress

User = get_user_model()
logger = logging.getLogger("apps.progress")


class ProgressService:
    """Business logic for tracking and updating student learning progress."""

    @staticmethod
    @transaction.atomic
    def update_lecture_position(
        user: User,
        lecture: Lecture,
        position_seconds: int,
        watched_seconds: int,
        video_duration: int,
    ) -> LectureProgress:
        """
        Update a student's position in a lecture video.
        Creates CourseProgress and LectureProgress records if they don't exist.
        Propagates completion changes up to CourseProgress.
        """
        course = lecture.section.course
        enrollment = EnrollmentService.get_enrollment(user, course)

        if not enrollment:
            raise PermissionError("User is not enrolled in this course.")

        course_progress, _ = CourseProgress.objects.get_or_create(
            enrollment=enrollment
        )

        lecture_progress, _ = LectureProgress.objects.get_or_create(
            course_progress=course_progress,
            lecture=lecture,
        )

        # Delegate update to model method (which enforces threshold)
        lecture_progress.update_position(position_seconds, watched_seconds, video_duration)

        # Update last accessed lecture on course progress
        course_progress.last_accessed_lecture = lecture
        course_progress.save(update_fields=["last_accessed_lecture", "last_activity_at"])

        logger.debug(
            "Progress updated: user=%s lecture=%s position=%s completion=%s%%",
            user.pk,
            lecture.pk,
            position_seconds,
            lecture_progress.completion_percentage,
        )

        # Check if course is now complete - trigger certificate generation
        if course_progress.is_completed:
            ProgressService._handle_course_completion(user, course_progress)

        return lecture_progress

    @staticmethod
    @transaction.atomic
    def mark_lecture_complete(user: User, lecture: Lecture) -> LectureProgress:
        """
        Manually mark a text/resource lecture as complete.
        Only used for non-video lectures.
        """
        course = lecture.section.course
        enrollment = EnrollmentService.get_enrollment(user, course)
        if not enrollment:
            raise PermissionError("User is not enrolled in this course.")

        course_progress, _ = CourseProgress.objects.get_or_create(enrollment=enrollment)
        lecture_progress, _ = LectureProgress.objects.get_or_create(
            course_progress=course_progress, lecture=lecture
        )

        now = timezone.now()
        if not lecture_progress.is_started:
            lecture_progress.is_started = True
            lecture_progress.started_at = now
        if not lecture_progress.is_completed:
            lecture_progress.is_completed = True
            lecture_progress.completed_at = now
            lecture_progress.completion_percentage = 100
        lecture_progress.save()

        course_progress.recalculate()

        if course_progress.is_completed:
            ProgressService._handle_course_completion(user, course_progress)

        return lecture_progress

    @staticmethod
    def _handle_course_completion(user: User, course_progress: CourseProgress) -> None:
        """
        Triggered when a student completes 100% of a course.
        Fires certificate generation asynchronously.
        """
        try:
            from apps.certificates.models import Certificate
            Certificate.objects.get_or_create(
                enrollment=course_progress.enrollment,
                defaults={
                    "user": user,
                    "course": course_progress.enrollment.course,
                    "completed_at": course_progress.completed_at or timezone.now(),
                },
            )
        except Exception as exc:
            logger.error("Certificate creation error: %s", exc)

        from apps.certificates.tasks import generate_certificate_task
        try:
            generate_certificate_task.delay(str(course_progress.enrollment_id))
            logger.info(
                "Certificate generation triggered: user=%s enrollment=%s",
                user.pk, course_progress.enrollment_id
            )
        except Exception as exc:
            # Non-critical: don't let certificate failure break progress
            logger.error("Certificate task error: %s", exc)

    @staticmethod
    def get_student_dashboard_data(user: User) -> dict:
        """
        Aggregate progress data for the student dashboard.
        Uses select_related / prefetch_related to avoid N+1 queries.
        """
        enrollments = (
            user.enrollments
            .select_related("course", "course__teacher", "course__category")
            .prefetch_related("progress")
            .filter(status="active")
            .order_by("-created_at")
        )

        courses_data = []
        total_learning_time = 0
        completed_courses = 0

        for enrollment in enrollments:
            try:
                cp = enrollment.progress
            except CourseProgress.DoesNotExist:
                cp = None

            completion = float(cp.completion_percentage) if cp else 0.0
            is_complete = cp.is_completed if cp else False
            learning_time = cp.total_learning_time_seconds if cp else 0

            if is_complete:
                completed_courses += 1
            total_learning_time += learning_time

            courses_data.append({
                "enrollment": enrollment,
                "course": enrollment.course,
                "progress": cp,
                "completion_percentage": completion,
                "is_completed": is_complete,
                "last_accessed_lecture": cp.last_accessed_lecture if cp else None,
            })

        # Sort to put in-progress courses first for "Continue Learning"
        in_progress = [c for c in courses_data if 0 < c["completion_percentage"] < 100]
        in_progress.sort(key=lambda x: x["progress"].last_activity_at if x["progress"] else 0, reverse=True)

        return {
            "courses": courses_data,
            "in_progress": in_progress[:3],  # top 3 for "continue learning" widget
            "total_courses": len(courses_data),
            "completed_courses": completed_courses,
            "total_learning_time_seconds": total_learning_time,
        }
