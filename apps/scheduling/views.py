"""Authenticated class booking and staff time-clock pages."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import UserRole

from .models import BookingStatus, Session, SessionBooking, SessionStatus, StaffShift
from .services import book_session, can_clock_in, cancel_booking, check_in_member, clock_in, clock_out


@login_required
def session_list(request):
    now = timezone.now()
    sessions = Session.objects.filter(
        status=SessionStatus.SCHEDULED, ends_at__gte=now,
    ).select_related("instructor", "course").annotate(
        seats_taken_count=Count("bookings", filter=Q(bookings__status=BookingStatus.BOOKED), distinct=True),
    ).order_by("starts_at")
    bookings = {
        booking.session_id: booking
        for booking in SessionBooking.objects.filter(member=request.user, session__in=sessions)
    }
    session_rows = [(session, bookings.get(session.id)) for session in sessions]
    return render(request, "scheduling/session_list.html", {
        "session_rows": session_rows,
        "can_book": request.user.role == UserRole.STUDENT,
    })


@login_required
@require_POST
def session_book(request, session_id):
    try:
        booking = book_session(session_id, request.user)
        if booking.status == BookingStatus.WAITLISTED:
            messages.info(request, "The class is full. You have been added to its waitlist.")
        else:
            messages.success(request, "Your place is booked.")
    except Session.DoesNotExist:
        messages.error(request, "That class could not be found.")
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, str(exc))
    return redirect("scheduling:sessions")


@login_required
@require_POST
def session_cancel(request, booking_id):
    booking = get_object_or_404(SessionBooking, pk=booking_id, member=request.user)
    try:
        cancel_booking(booking)
        messages.success(request, "Your booking has been cancelled.")
    except ValidationError as exc:
        messages.error(request, str(exc))
    return redirect("scheduling:sessions")


@login_required
@require_POST
def member_check_in(request, session_id):
    try:
        booking = check_in_member(
            session_id,
            request.user,
            request.POST.get("latitude"),
            request.POST.get("longitude"),
            request.POST.get("accuracy"),
        )
        messages.success(request, "Attendance recorded.")
    except Session.DoesNotExist:
        messages.error(request, "That class could not be found.")
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, str(exc))
    return redirect("scheduling:sessions")


@login_required
def staff_attendance(request):
    if not can_clock_in(request.user):
        raise PermissionDenied("Employee or instructor access is required to use the staff time clock.")
    open_shift = StaffShift.objects.filter(employee=request.user, checked_out_at__isnull=True).first()
    shifts = StaffShift.objects.filter(employee=request.user).order_by("-checked_in_at")[:30]
    return render(request, "scheduling/staff_attendance.html", {"open_shift": open_shift, "shifts": shifts})


@login_required
@require_POST
def staff_attendance_action(request):
    if not can_clock_in(request.user):
        raise PermissionDenied("Employee or instructor access is required to use the staff time clock.")
    fields = (request.POST.get("latitude"), request.POST.get("longitude"), request.POST.get("accuracy"))
    ip_address = request.META.get("REMOTE_ADDR")
    try:
        if request.POST.get("action") == "clock_out":
            clock_out(request.user, *fields, ip_address=ip_address)
            messages.success(request, "You have clocked out.")
        else:
            clock_in(request.user, *fields, ip_address=ip_address)
            messages.success(request, "You have clocked in.")
    except (ValidationError, PermissionDenied) as exc:
        messages.error(request, str(exc))
    return redirect("scheduling:staff_attendance")
