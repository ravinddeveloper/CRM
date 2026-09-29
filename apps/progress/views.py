"""Progress views - Student learning interface, video player, notes, completion."""
import logging
import time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.courses.models import Course, Section
from apps.enrollments.models import Enrollment
from apps.lectures.models import Attachment, Lecture, LectureNote, LectureVideo
from apps.progress.models import CourseProgress, LectureProgress, StudentNote
from apps.progress.services import ProgressService
from apps.storage.service import StorageService, safe_filename, validate_document_file

logger = logging.getLogger("apps.progress")


def _user_has_access(user, course: Course, lecture: Lecture = None) -> bool:
    """Helper to check if user has access to a course/lecture."""
    if not user.is_authenticated:
        return lecture is not None and lecture.is_free_preview

    if user.is_admin or (user.is_teacher and course.teacher_id == user.id):
        return True

    if Enrollment.objects.filter(user=user, course=course, status="active").exists():
        return True

    if lecture and lecture.is_free_preview:
        return True

    return False


@login_required(login_url="accounts:login")
def course_learn_view(request, course_slug):
    """
    Entry point for learning a course.
    Redirects to the last accessed lecture or the first published lecture.
    """
    course = get_object_or_404(
        Course.objects.select_related("teacher", "category"),
        slug=course_slug,
    )

    if not _user_has_access(request.user, course):
        messages.error(request, "You need an active enrollment to access this course.")
        return redirect("marketplace:course_detail", slug=course.slug)

    # Check for last accessed lecture in CourseProgress
    enrollment = Enrollment.objects.filter(user=request.user, course=course, status="active").first()
    if enrollment:
        course_progress = getattr(enrollment, "progress", None)
        if course_progress and course_progress.last_accessed_lecture_id:
            last_lec = course_progress.last_accessed_lecture
            if last_lec and last_lec.is_published:
                return redirect("learn:lecture", course_slug=course.slug, lecture_id=last_lec.id)

    # Otherwise find first published lecture
    first_lecture = (
        Lecture.objects.filter(section__course=course, is_published=True)
        .order_by("section__order", "order")
        .first()
    )

    if not first_lecture:
        messages.info(request, "This course currently has no published lectures.")
        return redirect("marketplace:course_detail", slug=course.slug)

    return redirect("learn:lecture", course_slug=course.slug, lecture_id=first_lecture.id)


def lecture_learn_view(request, course_slug, lecture_id):
    """
    Main learning interface: video player, curriculum sidebar, notes, resources, and progress.
    Supports free previews for unauthenticated/unenrolled users.
    """
    course = get_object_or_404(Course.objects.select_related("teacher"), slug=course_slug)
    lecture = get_object_or_404(
        Lecture.objects.select_related("section").prefetch_related("notes", "attachments"),
        id=lecture_id,
        section__course=course,
    )

    # Access control
    if not _user_has_access(request.user, course, lecture):
        if not request.user.is_authenticated:
            return redirect(f"{redirect('accounts:login').url}?next={request.path}")
        raise PermissionDenied("You do not have permission to view this lecture.")

    # All sections and published lectures for curriculum sidebar
    sections = (
        Section.objects.filter(course=course)
        .prefetch_related("lectures")
        .order_by("order")
    )

    all_lectures = []
    for s in sections:
        for lec in s.lectures.filter(is_published=True).order_by("order"):
            all_lectures.append(lec)

    # Find previous and next lecture
    prev_lecture = None
    next_lecture = None
    for idx, lec in enumerate(all_lectures):
        if lec.id == lecture.id:
            if idx > 0:
                prev_lecture = all_lectures[idx - 1]
            if idx < len(all_lectures) - 1:
                next_lecture = all_lectures[idx + 1]
            break

    # Student progress
    completed_lecture_ids = set()
    current_progress = None
    course_completion_pct = 0
    resume_position = 0

    if request.user.is_authenticated:
        enrollment = Enrollment.objects.filter(user=request.user, course=course, status="active").first()
        if enrollment:
            cp, _ = CourseProgress.objects.get_or_create(enrollment=enrollment)
            course_completion_pct = cp.completion_percentage

            # Update last accessed lecture
            cp.last_accessed_lecture = lecture
            cp.save(update_fields=["last_accessed_lecture", "last_activity_at"])

            # Completed lectures
            completed_lecture_ids = set(
                LectureProgress.objects.filter(
                    course_progress=cp, is_completed=True
                ).values_list("lecture_id", flat=True)
            )

            # Current lecture progress
            current_progress = LectureProgress.objects.filter(
                course_progress=cp, lecture=lecture
            ).first()

            if current_progress:
                resume_position = current_progress.video_position_seconds

    # Video signed URL (never expose direct S3/MinIO bucket link or Django static)
    video_url = None
    video_duration = 0
    try:
        video = lecture.video
        if video and video.storage_key:
            video_url = StorageService.get_presigned_url(video.storage_key, expires_in=7200)
            video_duration = video.duration_seconds
    except LectureVideo.DoesNotExist:
        video = None

    context = {
        "course": course,
        "lecture": lecture,
        "sections": sections,
        "video": video,
        "video_url": video_url,
        "video_duration": video_duration,
        "resume_position": resume_position,
        "prev_lecture": prev_lecture,
        "next_lecture": next_lecture,
        "completed_lecture_ids": completed_lecture_ids,
        "course_completion_pct": course_completion_pct,
        "is_completed": lecture.id in completed_lecture_ids,
        "notes": lecture.notes.all(),
        "attachments": lecture.attachments.all(),
        "student_notes": (
            StudentNote.objects.filter(user=request.user, lecture=lecture).order_by("-created_at")
            if request.user.is_authenticated
            else []
        ),
    }
    return render(request, "learn/lecture.html", context)


@login_required(login_url="accounts:login")
@require_http_methods(["POST"])
def mark_complete_view(request, course_slug, lecture_id):
    """Mark a lecture as complete manually."""
    course = get_object_or_404(Course, slug=course_slug)
    lecture = get_object_or_404(Lecture, id=lecture_id, section__course=course)

    if not _user_has_access(request.user, course):
        raise PermissionDenied("You are not enrolled in this course.")

    try:
        lp = ProgressService.mark_lecture_complete(request.user, lecture)
        course_progress = lp.course_progress
        return JsonResponse({
            "success": True,
            "completion_percentage": course_progress.completion_percentage,
            "is_course_completed": course_progress.is_completed,
        })
    except Exception as exc:
        logger.exception("Failed to mark lecture complete: %s", exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=400)


@login_required(login_url="accounts:login")
def download_resource_view(request, course_slug, lecture_id, resource_type, resource_id):
    """Download a lecture resource with a signed expiring URL."""
    course = get_object_or_404(Course, slug=course_slug)
    lecture = get_object_or_404(Lecture, id=lecture_id, section__course=course)

    if not _user_has_access(request.user, course, lecture):
        raise PermissionDenied("Not authorized to download this resource.")

    if resource_type == "note":
        item = get_object_or_404(LectureNote, id=resource_id, lecture=lecture)
    elif resource_type == "attachment":
        item = get_object_or_404(Attachment, id=resource_id, lecture=lecture)
    else:
        raise Http404("Invalid resource type.")

    if not item.storage_key:
        raise Http404("File not found.")

    download_url = StorageService.get_presigned_url(item.storage_key, expires_in=1800)
    return redirect(download_url)


@login_required(login_url="accounts:login")
@require_http_methods(["POST"])
def save_student_note_view(request, course_slug, lecture_id):
    """Save a typed note or uploaded study material document by the student."""
    course = get_object_or_404(Course, slug=course_slug)
    lecture = get_object_or_404(Lecture, id=lecture_id, section__course=course)

    if not _user_has_access(request.user, course, lecture):
        raise PermissionDenied("You must be enrolled to take notes.")

    title = request.POST.get("title", "").strip()
    content = request.POST.get("content", "").strip()
    raw_timestamp = request.POST.get("video_timestamp_seconds", "0")

    try:
        timestamp_sec = max(0, int(float(raw_timestamp)))
    except (ValueError, TypeError):
        timestamp_sec = 0

    note_file = request.FILES.get("note_file") or request.FILES.get("file")
    storage_key = ""
    orig_filename = ""
    file_size = 0

    if note_file:
        is_valid, error = validate_document_file(note_file)
        if not is_valid:
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"success": False, "error": error}, status=400)
            messages.error(request, error)
            return redirect("learn:lecture", course_slug=course.slug, lecture_id=lecture.id)

        clean_name = safe_filename(note_file.name)
        storage_key = f"courses/{course.id}/student_notes/{request.user.id}_{int(time.time())}_{clean_name}"
        StorageService.upload_file(
            storage_key,
            note_file,
            content_type=getattr(note_file, "content_type", "application/octet-stream")
        )
        orig_filename = note_file.name
        file_size = note_file.size

    if not content and not note_file:
        err_msg = "Please write some note text or upload a document."
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": False, "error": err_msg}, status=400)
        messages.error(request, err_msg)
        return redirect("learn:lecture", course_slug=course.slug, lecture_id=lecture.id)

    default_title = (
        f"Note @ {timestamp_sec // 60:02d}:{timestamp_sec % 60:02d}"
        if timestamp_sec > 0
        else (orig_filename or "Personal Note")
    )

    note = StudentNote.objects.create(
        user=request.user,
        lecture=lecture,
        course=course,
        title=title or default_title,
        content=content,
        storage_key=storage_key,
        original_filename=orig_filename,
        file_size_bytes=file_size,
        video_timestamp_seconds=timestamp_sec,
    )

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "success": True,
            "note": {
                "id": str(note.id),
                "title": note.title,
                "content": note.content,
                "timestamp": note.video_timestamp_seconds,
                "formatted_timestamp": note.formatted_timestamp,
                "has_file": bool(note.storage_key),
                "filename": note.original_filename,
            },
        })

    messages.success(request, "Note saved successfully.")
    return redirect("learn:lecture", course_slug=course.slug, lecture_id=lecture.id)


@login_required(login_url="accounts:login")
@require_http_methods(["POST"])
def delete_student_note_view(request, course_slug, lecture_id, note_id):
    """Delete a student's personal note and attached document."""
    course = get_object_or_404(Course, slug=course_slug)
    lecture = get_object_or_404(Lecture, id=lecture_id, section__course=course)
    note = get_object_or_404(StudentNote, id=note_id, user=request.user, lecture=lecture)

    if note.storage_key:
        try:
            StorageService.delete_file(note.storage_key)
        except Exception as exc:
            logger.warning("Could not delete note storage key %s: %s", note.storage_key, exc)

    note.delete()

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": True})

    messages.success(request, "Note deleted.")
    return redirect("learn:lecture", course_slug=course.slug, lecture_id=lecture.id)


@login_required(login_url="accounts:login")
def download_student_note_file_view(request, course_slug, lecture_id, note_id):
    """Download a file uploaded by the student with an expiring signed URL."""
    course = get_object_or_404(Course, slug=course_slug)
    lecture = get_object_or_404(Lecture, id=lecture_id, section__course=course)
    note = get_object_or_404(StudentNote, id=note_id, user=request.user, lecture=lecture)

    if not note.storage_key:
        raise Http404("No file attached to this note.")

    download_url = StorageService.get_presigned_url(note.storage_key, expires_in=1800)
    return redirect(download_url)
