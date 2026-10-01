"""Management views for the custom admin console."""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.admin_views import admin_required

from .forms import SessionManagementForm
from .models import BookingStatus, Session, SessionBooking, SessionStatus, StaffShift
from .services import get_shift_statistics


@admin_required
def schedule_attendance_view(request):
    now = timezone.now()
    sessions = Session.objects.select_related("instructor", "course").order_by("starts_at")[:100]
    bookings = SessionBooking.objects.select_related("session", "member").filter(
        session__starts_at__gte=now - timedelta(days=7),
    ).order_by("-booked_at")[:50]
    shifts = StaffShift.objects.select_related("employee").order_by("-checked_in_at")[:50]
    shift_stats = get_shift_statistics()

    context = {
        "active_tab": "schedule_attendance",
        "sessions": sessions,
        "bookings": bookings,
        "shifts": shifts,
        "upcoming_count": Session.objects.filter(status=SessionStatus.SCHEDULED, starts_at__gte=now).count(),
        "booked_count": SessionBooking.objects.filter(
            status=BookingStatus.BOOKED,
            session__status=SessionStatus.SCHEDULED,
            session__starts_at__gte=now,
        ).count(),
        "open_shifts_count": shift_stats["open_shifts_count"],
        "today_work_hours": shift_stats["formatted_today_hours"],
        "today_work_hours_decimal": shift_stats["today_hours"],
        "total_work_hours": shift_stats["formatted_total_hours"],
        "total_work_hours_decimal": shift_stats["total_hours"],
        "shift_stats": shift_stats,
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
