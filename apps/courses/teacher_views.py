"""Teacher dashboard views."""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.enrollments.models import Enrollment
from apps.lectures.models import Attachment, Lecture, LectureNote, LectureVideo

from .models import Course, CourseStatus, Section

logger = logging.getLogger("apps.courses")


def teacher_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_teacher or request.user.is_admin):
            from apps.common.views import error_403
            return error_403(request)
        return view_func(request, *args, **kwargs)
    return wrapper


def get_teacher_course(teacher, course_id):
    """Get a course that belongs to the teacher (or admin)."""
    if teacher.is_admin:
        return get_object_or_404(Course, id=course_id)
    return get_object_or_404(Course, id=course_id, teacher=teacher)


@teacher_required
def dashboard_view(request):
    teacher = request.user
    courses = Course.objects.filter(teacher=teacher) if teacher.is_teacher else Course.objects.all()
    courses = courses.annotate(student_count=Count("enrollments"))

    stats = {
        "total_courses": courses.count(),
        "published_courses": courses.filter(status=CourseStatus.PUBLISHED).count(),
        "draft_courses": courses.filter(status=CourseStatus.DRAFT).count(),
        "total_students": Enrollment.objects.filter(
            course__in=courses, status="active"
        ).values("user").distinct().count(),
    }

    recent_enrollments = Enrollment.objects.filter(
        course__in=courses
    ).select_related("user", "course").order_by("-created_at")[:10]

    context = {
        "courses": courses.order_by("-created_at")[:5],
        "stats": stats,
        "recent_enrollments": recent_enrollments,
    }
    return render(request, "dashboard/teacher/index.html", context)


@teacher_required
def course_list_view(request):
    teacher = request.user
    if teacher.is_admin:
        courses = Course.objects.all()
    else:
        courses = Course.objects.filter(teacher=teacher)
    courses = courses.select_related("category").annotate(student_count=Count("enrollments"))
    return render(request, "dashboard/teacher/course_list.html", {"courses": courses})


@teacher_required
@require_http_methods(["GET", "POST"])
def course_create_view(request):
    from .forms import CourseForm
    from .models import Category
    categories = Category.objects.filter(is_active=True).order_by("name")
    form = CourseForm(data=request.POST or None, files=request.FILES or None)
    if request.method == "POST" and form.is_valid():
        course = form.save(commit=False)
        course.teacher = request.user if request.user.is_teacher else course.teacher
        if not course.teacher_id:
            course.teacher = request.user
        course.save()
        form.save_m2m()
        messages.success(request, f"Course '{course.title}' created.")
        return redirect("teacher:course_edit", course_id=course.id)
    return render(request, "dashboard/teacher/course_form.html", {
        "form": form, "title": "Create Course", "categories": categories, "is_create": True
    })


@teacher_required
@require_http_methods(["GET", "POST"])
def course_edit_view(request, course_id):
    from .forms import CourseForm
    from .models import Category
    categories = Category.objects.filter(is_active=True).order_by("name")
    course = get_teacher_course(request.user, course_id)
    form = CourseForm(data=request.POST or None, files=request.FILES or None, instance=course)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Course updated.")
        return redirect("teacher:course_edit", course_id=course.id)
    sections = course.sections.prefetch_related("lectures").order_by("order")
    return render(request, "dashboard/teacher/course_form.html", {
        "form": form, "course": course, "sections": sections, "title": "Edit Course", "categories": categories, "is_create": False
    })


@teacher_required
@require_http_methods(["POST"])
def course_publish_view(request, course_id):
    course = get_teacher_course(request.user, course_id)
    if not course.sections.filter(is_published=True).exists():
        messages.error(request, "Add at least one published section before publishing.")
        return redirect("teacher:course_edit", course_id=course_id)
    course.publish()
    from apps.audit.models import AuditLog
    AuditLog.log("course_published", actor=request.user, obj=course, ip=request.META.get("REMOTE_ADDR"))
    messages.success(request, f"'{course.title}' is now published!")
    return redirect("teacher:course_edit", course_id=course_id)


@teacher_required
@require_http_methods(["POST"])
def course_unpublish_view(request, course_id):
    course = get_teacher_course(request.user, course_id)
    course.unpublish()
    messages.success(request, f"'{course.title}' has been unpublished.")
    return redirect("teacher:course_edit", course_id=course_id)


@teacher_required
def section_list_view(request, course_id):
    course = get_teacher_course(request.user, course_id)
    sections = course.sections.prefetch_related("lectures").order_by("order")
    return render(request, "dashboard/teacher/sections.html", {"course": course, "sections": sections})


@teacher_required
@require_http_methods(["GET", "POST"])
def section_create_view(request, course_id):
    from .forms import SectionForm
    course = get_teacher_course(request.user, course_id)
    form = SectionForm(data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        section = form.save(commit=False)
        section.course = course
        section.order = course.sections.count()
        section.save()
        messages.success(request, "Section created.")
        return redirect("teacher:course_edit", course_id=course_id)
    return render(request, "dashboard/teacher/section_form.html", {"form": form, "course": course})


@teacher_required
@require_http_methods(["GET", "POST"])
def lecture_create_view(request, section_id):
    from apps.lectures.forms import LectureForm
    section = get_object_or_404(Section, id=section_id)
    course = get_teacher_course(request.user, section.course_id)
    form = LectureForm(data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        lecture = form.save(commit=False)
        lecture.section = section
        lecture.order = section.lectures.count()
        lecture.save()
        messages.success(request, "Lecture created.")
        return redirect("teacher:lecture_edit", lecture_id=lecture.id)
    return render(request, "dashboard/teacher/lecture_form.html", {
        "form": form, "section": section, "course": course
    })


@teacher_required
@require_http_methods(["GET", "POST"])
def lecture_edit_view(request, lecture_id):
    from apps.lectures.forms import LectureForm
    lecture = get_object_or_404(Lecture, id=lecture_id)
    course = get_teacher_course(request.user, lecture.section.course_id)
    form = LectureForm(data=request.POST or None, instance=lecture)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Lecture updated.")
        return redirect("teacher:lecture_edit", lecture_id=lecture_id)
    return render(request, "dashboard/teacher/lecture_form.html", {
        "form": form, "lecture": lecture, "course": course
    })


@teacher_required
@require_http_methods(["GET", "POST"])
def video_upload_view(request, lecture_id):
    lecture = get_object_or_404(Lecture, id=lecture_id)
    get_teacher_course(request.user, lecture.section.course_id)

    if request.method == "POST":
        video_file = request.FILES.get("video")
        if not video_file:
            messages.error(request, "No video file provided.")
            return redirect("teacher:video_upload", lecture_id=lecture_id)

        from apps.storage.service import (
            get_storage_service,
            safe_filename,
            validate_video_file,
        )
        is_valid, error = validate_video_file(video_file)
        if not is_valid:
            messages.error(request, error)
            return redirect("teacher:video_upload", lecture_id=lecture_id)

        storage = get_storage_service()
        filename = safe_filename(video_file.name)
        key = storage.build_key("courses/videos", filename)
        storage.upload_file(key, video_file, video_file.content_type)

        LectureVideo.objects.update_or_create(
            lecture=lecture,
            defaults={
                "storage_key": key,
                "original_filename": video_file.name,
                "file_size_bytes": video_file.size,
                "mime_type": video_file.content_type,
            },
        )
        messages.success(request, "Video uploaded successfully.")
        return redirect("teacher:lecture_edit", lecture_id=lecture_id)

    return render(request, "dashboard/teacher/video_upload.html", {"lecture": lecture})


@teacher_required
@require_http_methods(["GET", "POST"])
def note_upload_view(request, lecture_id):
    lecture = get_object_or_404(Lecture, id=lecture_id)
    course = get_teacher_course(request.user, lecture.section.course_id)

    if request.method == "POST":
        note_file = request.FILES.get("note_file") or request.FILES.get("file")
        title = request.POST.get("title", "").strip()
        html_content = request.POST.get("html_content", "").strip()
        resource_type = request.POST.get("resource_type", "note").lower()

        if note_file:
            from apps.storage.service import (
                get_storage_service,
                safe_filename,
                validate_document_file,
            )
            is_valid, error = validate_document_file(note_file)
            if not is_valid:
                messages.error(request, error)
                return redirect("teacher:note_upload", lecture_id=lecture_id)

            storage = get_storage_service()
            filename = safe_filename(note_file.name)
            key = storage.build_key(f"courses/{course.id}/materials", filename)
            storage.upload_file(key, note_file, getattr(note_file, "content_type", "application/octet-stream"))

            if resource_type == "attachment" or filename.lower().endswith((".zip", ".tar", ".gz")):
                Attachment.objects.create(
                    lecture=lecture,
                    title=title or note_file.name,
                    storage_key=key,
                    original_filename=note_file.name,
                    mime_type=getattr(note_file, "content_type", "application/octet-stream"),
                    file_size_bytes=note_file.size,
                    is_downloadable=True,
                )
                messages.success(request, f"Attachment '{title or note_file.name}' uploaded.")
            else:
                note_type = "pdf" if filename.lower().endswith(".pdf") else "other"
                LectureNote.objects.create(
                    lecture=lecture,
                    title=title or note_file.name,
                    note_type=note_type,
                    storage_key=key,
                    original_filename=note_file.name,
                    file_size_bytes=note_file.size,
                    mime_type=getattr(note_file, "content_type", "application/pdf"),
                    is_downloadable=True,
                )
                messages.success(request, f"Lecture note '{title or note_file.name}' uploaded.")

            return redirect("teacher:lecture_edit", lecture_id=lecture_id)

        elif html_content:
            LectureNote.objects.create(
                lecture=lecture,
                title=title or "Lecture Note",
                note_type="html",
                html_content=html_content,
            )
            messages.success(request, "Lecture note created.")
            return redirect("teacher:lecture_edit", lecture_id=lecture_id)
        else:
            messages.error(request, "Please choose a file to upload or enter text content.")
            return redirect("teacher:note_upload", lecture_id=lecture_id)

    return render(request, "dashboard/teacher/note_form.html", {
        "lecture": lecture,
        "course": course,
    })


@teacher_required
@require_http_methods(["POST"])
def material_delete_view(request, resource_type, resource_id):
    """Delete a teacher-uploaded note or attachment."""
    from apps.storage.service import StorageService

    if resource_type == "note":
        item = get_object_or_404(LectureNote, id=resource_id)
        get_teacher_course(request.user, item.lecture.section.course_id)
        lecture_id = item.lecture_id
    elif resource_type == "attachment":
        item = get_object_or_404(Attachment, id=resource_id)
        get_teacher_course(request.user, item.lecture.section.course_id)
        lecture_id = item.lecture_id
    else:
        messages.error(request, "Invalid material type.")
        return redirect("teacher:course_list")

    if item.storage_key:
        try:
            StorageService.delete_file(item.storage_key)
        except Exception as exc:
            logger.warning("Failed to delete storage key %s: %s", item.storage_key, exc)

    item.delete()
    messages.success(request, "Study material deleted.")
    return redirect("teacher:lecture_edit", lecture_id=lecture_id)


@teacher_required
def course_students_view(request, course_id):
    course = get_teacher_course(request.user, course_id)
    enrollments = Enrollment.objects.filter(course=course).select_related(
        "user", "progress"
    ).order_by("-created_at")
    return render(request, "dashboard/teacher/course_students.html", {
        "course": course, "enrollments": enrollments
    })


@teacher_required
def analytics_view(request):
    return render(request, "dashboard/teacher/analytics.html")
