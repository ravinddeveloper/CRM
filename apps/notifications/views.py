"""Views for Announcements (Student, Teacher, and Admin)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.admin_views import admin_required
from apps.courses.models import Course
from apps.enrollments.models import Enrollment, EnrollmentStatus

from .forms import AnnouncementForm
from .models import Announcement, AnnouncementPriority


def announcement_list(request):
    """Public and student view of all announcements."""
    qs = Announcement.objects.filter(is_published=True).select_related("author", "course")

    # If student is logged in, show platform-wide announcements + announcements for their enrolled courses
    if request.user.is_authenticated and not request.user.is_admin:
        enrolled_course_ids = Enrollment.objects.filter(
            user=request.user, status=EnrollmentStatus.ACTIVE
        ).values_list("course_id", flat=True)
        qs = qs.filter(Q(course__isnull=True) | Q(course_id__in=enrolled_course_ids))
    elif not request.user.is_authenticated:
        # Anonymous users only see platform-wide announcements
        qs = qs.filter(course__isnull=True)

    priority_filter = request.GET.get("priority")
    if priority_filter in dict(AnnouncementPriority.choices):
        qs = qs.filter(priority=priority_filter)

    search_query = request.GET.get("q", "").strip()
    if search_query:
        qs = qs.filter(Q(title__icontains=search_query) | Q(content__icontains=search_query))

    pinned_announcements = qs.filter(is_pinned=True)
    recent_announcements = qs.filter(is_pinned=False)

    return render(
        request,
        "notifications/announcement_list.html",
        {
            "pinned_announcements": pinned_announcements,
            "recent_announcements": recent_announcements,
            "selected_priority": priority_filter,
            "search_query": search_query,
            "priorities": AnnouncementPriority.choices,
        },
    )


def announcement_detail(request, announcement_id):
    """Detailed view for a specific announcement."""
    announcement = get_object_or_404(
        Announcement.objects.select_related("author", "course"),
        pk=announcement_id,
    )
    if not announcement.is_published and not (
        request.user.is_authenticated and (request.user.is_admin or announcement.author_id == request.user.id)
    ):
        raise PermissionDenied("This announcement is not published.")

    # Related recent announcements
    related = Announcement.objects.filter(
        is_published=True
    ).exclude(pk=announcement.pk).order_by("-created_at")[:4]

    return render(
        request,
        "notifications/announcement_detail.html",
        {
            "announcement": announcement,
            "related_announcements": related,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN CONSOLE ANNOUNCEMENT MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@admin_required
def admin_announcement_list(request):
    """Admin dashboard list of all platform & course announcements with filter, sort, and CSV export."""
    announcements = Announcement.objects.select_related("author", "course")

    search_query = request.GET.get("q", "").strip()
    if search_query:
        announcements = announcements.filter(
            Q(title__icontains=search_query)
            | Q(content__icontains=search_query)
            | Q(author__email__icontains=search_query)
        )

    priority_filter = request.GET.get("priority", "").strip()
    if priority_filter in dict(AnnouncementPriority.choices):
        announcements = announcements.filter(priority=priority_filter)

    scope_filter = request.GET.get("scope", "").strip()
    if scope_filter == "platform":
        announcements = announcements.filter(course__isnull=True)
    elif scope_filter == "course":
        announcements = announcements.filter(course__isnull=False)

    sort = request.GET.get("sort", "newest").strip()
    if sort == "oldest":
        announcements = announcements.order_by("created_at")
    elif sort == "views":
        announcements = announcements.order_by("-views_count")
    elif sort == "title":
        announcements = announcements.order_by("title")
    else:
        announcements = announcements.order_by("-is_pinned", "-created_at")

    # CSV Export
    if request.GET.get("export") == "csv":
        from apps.common.exports import export_as_csv
        headers = [
            "Title", "Scope", "Course Target", "Priority", "Author Name",
            "Author Email", "Views Count", "Pinned", "Published", "Created At"
        ]
        rows = [
            [
                a.title,
                "Platform-Wide" if not a.course else "Course Specific",
                a.course.title if a.course else "All Learners",
                a.get_priority_display(),
                a.author.full_name if a.author else "",
                a.author.email if a.author else "",
                a.views_count,
                "Yes" if a.is_pinned else "No",
                "Yes" if a.is_published else "No",
                a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
            ]
            for a in announcements
        ]
        return export_as_csv("announcements_export.csv", headers, rows)

    total_count = Announcement.objects.count()
    platform_count = Announcement.objects.filter(course__isnull=True).count()
    course_count = Announcement.objects.filter(course__isnull=False).count()
    pinned_count = Announcement.objects.filter(is_pinned=True).count()

    return render(
        request,
        "dashboard/admin/announcements/list.html",
        {
            "active_tab": "announcements",
            "announcements": announcements,
            "search_query": search_query,
            "selected_priority": priority_filter,
            "selected_scope": scope_filter,
            "sort": sort,
            "priorities": AnnouncementPriority.choices,
            "total_count": total_count,
            "platform_count": platform_count,
            "course_count": course_count,
            "pinned_count": pinned_count,
        },
    )



@admin_required
def admin_announcement_create(request):
    """Create a new platform or course announcement."""
    form = AnnouncementForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        announcement = form.save(commit=False)
        announcement.author = request.user
        announcement.save()
        messages.success(request, f'Announcement "{announcement.title}" created successfully.')
        return redirect("admin_panel:announcement_list")

    return render(
        request,
        "dashboard/admin/announcements/form.html",
        {
            "active_tab": "announcements",
            "form": form,
            "page_title": "Create Announcement",
            "action_button": "Publish Announcement",
        },
    )


@admin_required
def admin_announcement_edit(request, announcement_id):
    """Edit an existing announcement."""
    announcement = get_object_or_404(Announcement, pk=announcement_id)
    form = AnnouncementForm(request.POST or None, instance=announcement, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f'Announcement "{announcement.title}" updated.')
        return redirect("admin_panel:announcement_list")

    return render(
        request,
        "dashboard/admin/announcements/form.html",
        {
            "active_tab": "announcements",
            "form": form,
            "announcement": announcement,
            "page_title": f"Edit {announcement.title}",
            "action_button": "Update Announcement",
        },
    )


@admin_required
@require_POST
def admin_announcement_delete(request, announcement_id):
    """Delete an announcement."""
    announcement = get_object_or_404(Announcement, pk=announcement_id)
    title = announcement.title
    announcement.delete()
    messages.success(request, f'Announcement "{title}" deleted.')
    return redirect("admin_panel:announcement_list")


# ─────────────────────────────────────────────────────────────────────────────
# TEACHER CONSOLE ANNOUNCEMENT MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def teacher_announcement_list(request):
    if not (request.user.is_teacher or request.user.is_admin):
        raise PermissionDenied("Instructor access required.")

    announcements = Announcement.objects.filter(
        author=request.user
    ).select_related("course").order_by("-created_at")

    return render(
        request,
        "dashboard/teacher/announcements/list.html",
        {
            "active_tab": "announcements",
            "announcements": announcements,
        },
    )


@login_required
def teacher_announcement_create(request):
    if not (request.user.is_teacher or request.user.is_admin):
        raise PermissionDenied("Instructor access required.")

    form = AnnouncementForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        announcement = form.save(commit=False)
        announcement.author = request.user
        announcement.save()
        messages.success(request, f'Announcement "{announcement.title}" published.')
        return redirect("teacher:announcement_list")

    return render(
        request,
        "dashboard/teacher/announcements/form.html",
        {
            "active_tab": "announcements",
            "form": form,
            "page_title": "Create Course Announcement",
        },
    )
