"""
Progress API views.

REST/AJAX endpoints for video playback and lecture progress tracking.
Enforces server-side authorization and enrollment verification.
"""
import logging

from django.shortcuts import get_object_or_404
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.courses.models import Course
from apps.enrollments.services import EnrollmentService
from apps.lectures.models import Lecture
from apps.progress.models import CourseProgress, LectureProgress
from apps.progress.services import ProgressService

logger = logging.getLogger("apps.progress")


def _error_response(message: str, code: str = "ERROR", status_code: int = 400) -> Response:
    return Response(
        {"success": False, "error": {"code": code, "message": message}},
        status=status_code,
    )


def _check_authenticated(request) -> Response | None:
    if not request.user or not request.user.is_authenticated:
        return _error_response("Authentication required.", code="UNAUTHENTICATED", status_code=403)
    return None


@api_view(["POST"])
@authentication_classes([SessionAuthentication, JWTAuthentication])
@permission_classes([AllowAny])
def update_video_position(request, lecture_id: str) -> Response:
    """Update playback position for a lecture."""
    auth_err = _check_authenticated(request)
    if auth_err:
        return auth_err

    lecture = get_object_or_404(Lecture, pk=lecture_id, is_published=True)
    course = lecture.section.course

    if not lecture.is_free_preview:
        if not EnrollmentService.has_access(request.user, course):
            return _error_response(
                "You do not have access to this course.",
                code="COURSE_ACCESS_DENIED",
                status_code=403,
            )

    data = request.data
    try:
        position_seconds = int(data.get("position_seconds", 0))
        watched_seconds = int(data.get("watched_seconds", 0))
        video_duration = int(data.get("video_duration", 0))
    except (ValueError, TypeError) as exc:
        return _error_response(f"Invalid payload: {exc}", status_code=400)

    if position_seconds < 0 or watched_seconds < 0 or video_duration < 0:
        return _error_response("Invalid time values.", status_code=400)
    if video_duration > 0 and position_seconds > video_duration + 5:
        position_seconds = video_duration
    if video_duration > 0 and watched_seconds > video_duration + 5:
        watched_seconds = video_duration

    if lecture.is_free_preview and not EnrollmentService.has_access(request.user, course):
        return Response({
            "success": True,
            "lecture_id": str(lecture_id),
            "position_seconds": position_seconds,
            "completion_percentage": "0.00",
            "is_completed": False,
            "course_completion_percentage": "0.00",
            "is_free_preview": True,
        })

    try:
        lecture_progress = ProgressService.update_lecture_position(
            user=request.user,
            lecture=lecture,
            position_seconds=position_seconds,
            watched_seconds=watched_seconds,
            video_duration=video_duration,
        )
    except PermissionError as exc:
        return _error_response(str(exc), code="COURSE_ACCESS_DENIED", status_code=403)
    except Exception as exc:
        logger.error("Progress update error for user=%s lecture=%s: %s", request.user.pk, lecture_id, exc)
        return _error_response("Failed to update progress.", status_code=500)

    return Response({
        "success": True,
        "lecture_id": str(lecture_id),
        "position_seconds": lecture_progress.video_position_seconds,
        "completion_percentage": str(lecture_progress.completion_percentage),
        "is_completed": lecture_progress.is_completed,
        "course_completion_percentage": str(
            lecture_progress.course_progress.completion_percentage
        ),
    })


@api_view(["GET"])
@authentication_classes([SessionAuthentication, JWTAuthentication])
@permission_classes([AllowAny])
def get_resume_position(request, lecture_id: str) -> Response:
    """Return last saved playback position for a lecture."""
    auth_err = _check_authenticated(request)
    if auth_err:
        return auth_err

    lecture = get_object_or_404(Lecture, pk=lecture_id, is_published=True)
    course = lecture.section.course

    if not lecture.is_free_preview:
        if not EnrollmentService.has_access(request.user, course):
            return _error_response(
                "You do not have access to this lecture.",
                code="COURSE_ACCESS_DENIED",
                status_code=403,
            )

    try:
        enrollment = EnrollmentService.get_enrollment(request.user, course)
        if not enrollment:
            return Response({"success": True, "position_seconds": 0, "is_completed": False})

        course_progress = CourseProgress.objects.filter(enrollment=enrollment).first()
        if not course_progress:
            return Response({"success": True, "position_seconds": 0, "is_completed": False})

        lp = LectureProgress.objects.filter(
            course_progress=course_progress, lecture=lecture
        ).first()

        if not lp:
            return Response({"success": True, "position_seconds": 0, "is_completed": False})

        return Response({
            "success": True,
            "position_seconds": lp.video_position_seconds,
            "watched_seconds": lp.watched_duration_seconds,
            "completion_percentage": str(lp.completion_percentage),
            "is_completed": lp.is_completed,
            "course_completion_percentage": str(course_progress.completion_percentage),
        })
    except Exception as exc:
        logger.error("Resume position error for user=%s lecture=%s: %s", request.user.pk, lecture_id, exc)
        return _error_response("Failed to retrieve progress.", status_code=500)


@api_view(["POST"])
@authentication_classes([SessionAuthentication, JWTAuthentication])
@permission_classes([AllowAny])
def mark_lecture_complete(request, lecture_id: str) -> Response:
    """Manually mark non-video lecture as complete."""
    auth_err = _check_authenticated(request)
    if auth_err:
        return auth_err

    lecture = get_object_or_404(Lecture, pk=lecture_id, is_published=True)
    course = lecture.section.course

    if not EnrollmentService.has_access(request.user, course):
        return _error_response(
            "You do not have access to this course.",
            code="COURSE_ACCESS_DENIED",
            status_code=403,
        )

    if hasattr(lecture, "video") and lecture.video:
        return _error_response(
            "Video lectures are marked complete based on watch time.",
            code="VIDEO_COMPLETION_ONLY",
            status_code=400,
        )

    try:
        lecture_progress = ProgressService.mark_lecture_complete(
            user=request.user, lecture=lecture
        )
    except Exception as exc:
        logger.error("Mark complete error for user=%s lecture=%s: %s", request.user.pk, lecture_id, exc)
        return _error_response("Failed to mark lecture complete.", status_code=500)

    return Response({
        "success": True,
        "lecture_id": str(lecture_id),
        "is_completed": lecture_progress.is_completed,
        "course_completion_percentage": str(
            lecture_progress.course_progress.completion_percentage
        ),
        "course_is_completed": lecture_progress.course_progress.is_completed,
    })


@api_view(["GET"])
@authentication_classes([SessionAuthentication, JWTAuthentication])
@permission_classes([AllowAny])
def get_course_progress(request, course_id: str) -> Response:
    """Return student course progress for the learning view / dashboard."""
    auth_err = _check_authenticated(request)
    if auth_err:
        return auth_err

    course = get_object_or_404(Course, pk=course_id)

    if not EnrollmentService.has_access(request.user, course):
        return _error_response("No access.", code="COURSE_ACCESS_DENIED", status_code=403)

    enrollment = EnrollmentService.get_enrollment(request.user, course)
    if not enrollment:
        return Response({"success": True, "enrolled": False})

    course_progress = CourseProgress.objects.filter(enrollment=enrollment).first()
    if not course_progress:
        return Response({
            "success": True,
            "enrolled": True,
            "completion_percentage": "0.00",
            "completed_lectures": 0,
            "total_lectures": 0,
        })

    lecture_data = []
    for lp in course_progress.lecture_progresses.select_related("lecture").all():
        lecture_data.append({
            "lecture_id": str(lp.lecture_id),
            "lecture_title": lp.lecture.title,
            "is_started": lp.is_started,
            "is_completed": lp.is_completed,
            "completion_percentage": str(lp.completion_percentage),
            "position_seconds": lp.video_position_seconds,
        })

    return Response({
        "success": True,
        "enrolled": True,
        "completion_percentage": str(course_progress.completion_percentage),
        "completed_lectures": course_progress.completed_lectures,
        "total_lectures": course_progress.total_lectures,
        "total_learning_time_seconds": course_progress.total_learning_time_seconds,
        "is_completed": course_progress.is_completed,
        "last_accessed_lecture_id": (
            str(course_progress.last_accessed_lecture_id)
            if course_progress.last_accessed_lecture_id
            else None
        ),
        "lectures": lecture_data,
    })


@api_view(["POST"])
@authentication_classes([SessionAuthentication, JWTAuthentication])
@permission_classes([AllowAny])
def heartbeat_view(request) -> Response:
    """
    Heartbeat ping sent by video player every 15 seconds.
    Updates playback position, cumulative watch time, and verifies completion thresholds.
    """
    auth_err = _check_authenticated(request)
    if auth_err:
        return auth_err

    data = request.data
    lecture_id = data.get("lecture_id")
    if not lecture_id:
        return _error_response("lecture_id is required.", code="MISSING_PARAM", status_code=400)

    lecture = get_object_or_404(Lecture, pk=lecture_id, is_published=True)
    course = lecture.section.course

    if not lecture.is_free_preview and not EnrollmentService.has_access(request.user, course):
        return _error_response("You do not have access to this course.", code="COURSE_ACCESS_DENIED", status_code=403)

    try:
        position_seconds = int(data.get("position_seconds", 0))
        watched_seconds = int(data.get("watched_seconds", 0))
        video_duration = int(data.get("video_duration", 0))
    except (ValueError, TypeError) as exc:
        return _error_response(f"Invalid payload: {exc}", status_code=400)

    if position_seconds < 0 or watched_seconds < 0 or video_duration < 0:
        return _error_response("Invalid time values.", status_code=400)
    if video_duration > 0 and position_seconds > video_duration + 5:
        position_seconds = video_duration
    if video_duration > 0 and watched_seconds > video_duration + 5:
        watched_seconds = video_duration

    if lecture.is_free_preview and not EnrollmentService.has_access(request.user, course):
        return Response({
            "success": True,
            "lecture_id": str(lecture_id),
            "position_seconds": position_seconds,
            "completion_percentage": "0.00",
            "is_completed": False,
            "course_completion_percentage": "0.00",
            "is_free_preview": True,
        })

    try:
        lecture_progress = ProgressService.update_lecture_position(
            user=request.user,
            lecture=lecture,
            position_seconds=position_seconds,
            watched_seconds=watched_seconds,
            video_duration=video_duration,
        )
    except PermissionError as exc:
        return _error_response(str(exc), code="COURSE_ACCESS_DENIED", status_code=403)
    except Exception as exc:
        logger.error("Heartbeat error for user=%s lecture=%s: %s", request.user.pk, lecture_id, exc)
        return _error_response("Failed to update heartbeat progress.", status_code=500)

    return Response({
        "success": True,
        "lecture_id": str(lecture_id),
        "position_seconds": lecture_progress.video_position_seconds,
        "completion_percentage": str(lecture_progress.completion_percentage),
        "is_completed": lecture_progress.is_completed,
        "course_completion_percentage": str(
            lecture_progress.course_progress.completion_percentage
        ),
        "course_is_completed": lecture_progress.course_progress.is_completed,
    })
