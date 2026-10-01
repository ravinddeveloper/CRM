"""Student views - dashboard, learning view, certificates, orders."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.enrollments.models import Enrollment


def _role_redirect(user):
    if user.is_admin:
        return redirect("admin_panel:dashboard")
    if user.is_teacher:
        return redirect("teacher:dashboard")
    if user.is_employee:
        return redirect("scheduling:staff_attendance")
    return None


@login_required(login_url="accounts:login")
def student_dashboard_view(request):
    """Student dashboard showing enrolled courses, progress, and stats."""
    user = request.user
    if not user.is_student:
        return _role_redirect(user) or redirect("dashboard:redirect")
    enrollments = (
        Enrollment.objects.filter(user=user, status="active")
        .select_related("course", "course__teacher")
        .prefetch_related("progress")
        .order_by("-created_at")
    )

    total_courses = enrollments.count()
    completed_count = 0
    in_progress_count = 0
    total_time_seconds = 0

    enrollment_list = []
    for enr in enrollments:
        progress = getattr(enr, "progress", None)
        comp_pct = progress.completion_percentage if progress else 0
        if progress and progress.is_completed:
            completed_count += 1
        elif comp_pct > 0:
            in_progress_count += 1

        if progress:
            total_time_seconds += progress.total_learning_time_seconds

        enrollment_list.append({
            "enrollment": enr,
            "course": enr.course,
            "progress": progress,
            "completion_percentage": comp_pct,
        })

    from apps.progress.models import StudentNote
    student_notes = (
        StudentNote.objects.filter(user=user)
        .select_related("course", "lecture")
        .order_by("-created_at")[:10]
    )

    in_progress = [item for item in enrollment_list if 0 < item["completion_percentage"] < 100]

    context = {
        "enrollments": enrollments,
        "courses": enrollment_list,
        "in_progress": in_progress,
        "student_notes": student_notes,
        "stats": {
            "total_courses": total_courses,
            "completed_courses": completed_count,
            "in_progress_count": in_progress_count,
            "total_hours": round(total_time_seconds / 3600, 1),
            "notes_count": StudentNote.objects.filter(user=user).count(),
        },
    }
    return render(request, "dashboard/student/dashboard.html", context)


@login_required(login_url="accounts:login")
def student_orders_view(request):
    """Student order history."""
    if not request.user.is_student:
        return _role_redirect(request.user) or redirect("dashboard:redirect")
    from apps.orders.models import Order
    orders = (
        Order.objects.filter(user=request.user)
        .prefetch_related("items", "items__course")
        .order_by("-created_at")
    )
    return render(request, "dashboard/student/orders.html", {"orders": orders})
