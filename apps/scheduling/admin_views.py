"""Management views for the custom admin console."""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from django.contrib.auth import get_user_model

from apps.accounts.admin_views import admin_required

from .forms import SessionManagementForm
from .models import BookingStatus, Session, SessionBooking, SessionStatus, StaffShift
from .services import get_shift_statistics


@admin_required
def schedule_attendance_view(request):
    now = timezone.now()
    tab = request.GET.get("tab")
    if not tab:
        tab = "shifts" if request.GET.get("employee") else "all"
    if tab not in {"all", "schedule", "attendance", "shifts"}:
        tab = "all"

    # Search, sort & filters for Sessions
    sessions_qs = Session.objects.select_related("instructor", "course")
    session_status = request.GET.get("status", "").strip()
    session_q = request.GET.get("session_q", "").strip()
    session_sort = request.GET.get("session_sort", "soonest").strip()

    if session_status:
        sessions_qs = sessions_qs.filter(status=session_status)
    if session_q:
        sessions_qs = sessions_qs.filter(title__icontains=session_q)

    if session_sort == "latest":
        sessions_qs = sessions_qs.order_by("-starts_at")
    elif session_sort == "title":
        sessions_qs = sessions_qs.order_by("title")
    elif session_sort == "capacity":
        sessions_qs = sessions_qs.order_by("-capacity")
    else:
        sessions_qs = sessions_qs.order_by("starts_at")

    # Search, sort & filters for Member Bookings
    bookings_qs = SessionBooking.objects.select_related("session", "member")
    booking_status = request.GET.get("booking_status", "").strip()
    booking_q = request.GET.get("booking_q", "").strip()
    booking_sort = request.GET.get("booking_sort", "newest").strip()

    if booking_status:
        bookings_qs = bookings_qs.filter(status=booking_status)
    if booking_q:
        bookings_qs = bookings_qs.filter(
            models.Q(member__first_name__icontains=booking_q)
            | models.Q(member__last_name__icontains=booking_q)
            | models.Q(member__email__icontains=booking_q)
            | models.Q(session__title__icontains=booking_q)
        )

    if booking_sort == "oldest":
        bookings_qs = bookings_qs.order_by("booked_at")
    elif booking_sort == "member":
        bookings_qs = bookings_qs.order_by("member__first_name", "member__last_name")
    else:
        bookings_qs = bookings_qs.order_by("-booked_at")

    # Individual employee filtering & stats calculation
    employee_id = request.GET.get("employee")
    selected_employee = None
    shifts_qs = StaffShift.objects.select_related("employee")
    shift_sort = request.GET.get("shift_sort", "newest").strip()

    if employee_id:
        try:
            selected_employee = get_user_model().objects.get(pk=employee_id)
            shifts_qs = shifts_qs.filter(employee=selected_employee)
        except (ValueError, get_user_model().DoesNotExist):
            selected_employee = None

    if shift_sort == "oldest":
        shifts_qs = shifts_qs.order_by("checked_in_at")
    elif shift_sort == "employee":
        shifts_qs = shifts_qs.order_by("employee__first_name", "employee__last_name")
    else:
        shifts_qs = shifts_qs.order_by("-checked_in_at")

    # CSV Exports
    export_type = request.GET.get("export", "").strip()
    if export_type in {"sessions", "sessions_csv"} or (export_type == "csv" and tab == "schedule"):
        from apps.common.exports import export_as_csv
        headers = ["Title", "Course", "Instructor Name", "Instructor Email", "Starts At", "Ends At", "Capacity", "Location", "Status"]
        rows = [
            [
                s.title,
                s.course.title if s.course else "General",
                s.instructor.full_name if s.instructor else "",
                s.instructor.email if s.instructor else "",
                s.starts_at.strftime("%Y-%m-%d %H:%M") if s.starts_at else "",
                s.ends_at.strftime("%Y-%m-%d %H:%M") if s.ends_at else "",
                s.capacity,
                s.location,
                s.get_status_display(),
            ]
            for s in sessions_qs
        ]
        return export_as_csv("sessions_schedule_export.csv", headers, rows)

    if export_type in {"bookings", "bookings_csv"} or (export_type == "csv" and tab == "attendance"):
        from apps.common.exports import export_as_csv
        headers = ["Member Name", "Member Email", "Session Title", "Instructor", "Status", "Booked At", "Checked In At"]
        rows = [
            [
                b.member.full_name if b.member else "",
                b.member.email if b.member else "",
                b.session.title if b.session else "",
                b.session.instructor.full_name if (b.session and b.session.instructor) else "",
                b.get_status_display(),
                b.booked_at.strftime("%Y-%m-%d %H:%M") if b.booked_at else "",
                b.checked_in_at.strftime("%Y-%m-%d %H:%M") if b.checked_in_at else "Not Checked In",
            ]
            for b in bookings_qs
        ]
        return export_as_csv("attendance_bookings_export.csv", headers, rows)

    if export_type in {"shifts", "shifts_csv"} or (export_type == "csv" and tab == "shifts"):
        from apps.common.exports import export_as_csv
        headers = ["Employee Name", "Employee Email", "Checked In At", "Checked Out At", "Total Hours", "Notes"]
        rows = [
            [
                sh.employee.full_name if sh.employee else "",
                sh.employee.email if sh.employee else "",
                sh.checked_in_at.strftime("%Y-%m-%d %H:%M") if sh.checked_in_at else "",
                sh.checked_out_at.strftime("%Y-%m-%d %H:%M") if sh.checked_out_at else "Ongoing",
                f"{sh.hours:.2f}" if sh.hours is not None else "In Progress",
                sh.notes or "",
            ]
            for sh in shifts_qs
        ]
        return export_as_csv("staff_shifts_export.csv", headers, rows)

    sessions = sessions_qs[:100]
    bookings = bookings_qs[:100]
    shifts = shifts_qs[:100]

    # Calculate statistics based on selected employee (if any) and get full individual breakdown
    shift_stats = get_shift_statistics(employee=selected_employee)
    all_shift_stats = get_shift_statistics() if selected_employee else shift_stats
    individual_stats = all_shift_stats.get("individual_stats", [])

    total_sessions_count = Session.objects.count()
    total_bookings_count = SessionBooking.objects.count()


    context = {
        "active_tab": tab,
        "current_tab": tab,
        "sessions": sessions,
        "session_status": session_status,
        "session_q": session_q,
        "session_sort": session_sort,
        "total_sessions_count": total_sessions_count,
        "bookings": bookings,
        "booking_status": booking_status,
        "booking_q": booking_q,
        "booking_sort": booking_sort,
        "total_bookings_count": total_bookings_count,
        "shifts": shifts,
        "shift_sort": shift_sort,
        "selected_employee": selected_employee,
        "selected_employee_id": str(selected_employee.id) if selected_employee else "",
        "upcoming_count": Session.objects.filter(status=SessionStatus.SCHEDULED, starts_at__gte=now).count(),
        "booked_count": SessionBooking.objects.filter(
            status=BookingStatus.BOOKED,
            session__status=SessionStatus.SCHEDULED,
            session__starts_at__gte=now,
        ).count(),
        "checked_in_count": SessionBooking.objects.filter(checked_in_at__isnull=False).count(),
        "open_shifts_count": shift_stats["open_shifts_count"],
        "today_work_hours": shift_stats["formatted_today_hours"],
        "today_work_hours_decimal": shift_stats["today_hours"],
        "total_work_hours": shift_stats["formatted_total_hours"],
        "total_work_hours_decimal": shift_stats["total_hours"],
        "shift_stats": shift_stats,
        "all_shift_stats": all_shift_stats,
        "individual_stats": individual_stats,
    }
    return render(request, "dashboard/admin/scheduling.html", context)


@admin_required
def session_create_view(request):
    form = SessionManagementForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        session = form.save()
        messages.success(request, f'Created "{session.title}".')
        return redirect("admin_panel:schedule_attendance")
    return render(request, "dashboard/admin/scheduling_form.html", {
        "active_tab": "schedule_attendance", "form": form, "page_title": "Create a class or session",
    })


@admin_required
def session_edit_view(request, session_id):
    session = get_object_or_404(Session, pk=session_id)
    form = SessionManagementForm(request.POST or None, instance=session)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f'Updated "{session.title}".')
        return redirect("admin_panel:schedule_attendance")
    return render(request, "dashboard/admin/scheduling_form.html", {
        "active_tab": "schedule_attendance", "form": form, "page_title": f"Edit {session.title}",
    })


@admin_required
@require_POST
def session_status_action(request, session_id):
    with transaction.atomic():
        session = get_object_or_404(Session.objects.select_for_update(), pk=session_id)
        status = request.POST.get("status")
        if status not in {SessionStatus.SCHEDULED, SessionStatus.CANCELLED, SessionStatus.COMPLETED}:
            raise PermissionDenied("Invalid session status.")
        session.status = status
        session.save(update_fields=["status", "updated_at"])
        if status != SessionStatus.SCHEDULED:
            SessionBooking.objects.filter(
                session=session, status__in=[BookingStatus.BOOKED, BookingStatus.WAITLISTED]
            ).update(status=BookingStatus.CANCELLED)
    messages.success(request, f'Updated "{session.title}".')
    return redirect("admin_panel:schedule_attendance")
