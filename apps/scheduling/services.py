"""Business rules for scheduling, reservations, and attendance."""
import math
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.common.models import get_platform_settings

from .models import (
    BookingStatus,
    MemberMembership,
    MembershipStatus,
    Session,
    SessionBooking,
    SessionStatus,
    StaffShift,
)


def _config(name, fallback):
    config = get_platform_settings()
    return config.get(name, fallback) if isinstance(config, dict) else getattr(config, name, fallback)


def _coordinate_pair(latitude, longitude, accuracy):
    try:
        lat = Decimal(str(latitude))
        lon = Decimal(str(longitude))
        accuracy_m = Decimal(str(accuracy)) if accuracy not in (None, "") else None
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError("Your device did not provide a valid location. Enable location access and try again.")
    if not lat.is_finite() or not lon.is_finite() or (accuracy_m is not None and not accuracy_m.is_finite()):
        raise ValidationError("Your device did not provide a valid location. Enable location access and try again.")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValidationError("The location coordinates are outside the valid range.")
    if accuracy_m is not None and (accuracy_m < 0 or accuracy_m > _config("max_location_accuracy_meters", 150)):
        raise ValidationError("Your location accuracy is too low. Move to an open area and try again.")
    return lat, lon, accuracy_m


def distance_meters(lat1, lon1, lat2, lon2):
    """Calculate great-circle distance between two latitude/longitude pairs."""
    radius = 6_371_000
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    delta_phi = math.radians(float(lat2) - float(lat1))
    delta_lambda = math.radians(float(lon2) - float(lon1))
    value = min(1.0, max(0.0, math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2))
    return int(round(radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))))


def _validate_location(latitude, longitude, accuracy, target_latitude, target_longitude, radius):
    if latitude in (None, "") or longitude in (None, ""):
        raise ValidationError("Location is required for this attendance action. Allow location access and try again.")
    lat, lon, accuracy_m = _coordinate_pair(latitude, longitude, accuracy)
    if target_latitude is None or target_longitude is None:
        raise ValidationError("The business has not configured its attendance location yet. Contact an administrator.")
    distance = distance_meters(lat, lon, target_latitude, target_longitude)
    if distance > radius:
        raise ValidationError(f"You are about {distance} metres away. Check-in is allowed within {radius} metres.")
    return distance, int(accuracy_m) if accuracy_m is not None else None


def _member_has_active_membership(user):
    now = timezone.now()
    return MemberMembership.objects.filter(
        member=user,
        plan__is_active=True,
        status=MembershipStatus.ACTIVE,
        starts_at__lte=now,
    ).filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))


@transaction.atomic
def book_session(session_id, member):
    session = Session.objects.select_for_update().select_related("course").get(pk=session_id)
    if member.role != UserRole.STUDENT:
        raise PermissionDenied("Only member accounts can book a class.")
    if not session.is_open or session.starts_at <= timezone.now():
        raise ValidationError("This class is not open for booking.")
    if session.membership_required and not _member_has_active_membership(member).exists():
        raise PermissionDenied("An active membership is required to book this class.")
    if session.course_id:
        from apps.enrollments.models import Enrollment
        if session.course.effective_price > 0:
            enrollment = Enrollment.objects.filter(user=member, course=session.course).first()
            if not enrollment or not enrollment.is_active:
                raise PermissionDenied("Purchase or enroll in the linked course before booking this class.")

    booking, created = SessionBooking.objects.get_or_create(session=session, member=member)
    if not created and booking.status == BookingStatus.BOOKED:
        return booking
    active_count = SessionBooking.objects.filter(session=session, status=BookingStatus.BOOKED).count()
    full = bool(session.capacity and active_count >= session.capacity)
    if full and not session.allow_waitlist:
        raise ValidationError("This class is full and does not have a waitlist.")
    booking.status = BookingStatus.WAITLISTED if full else BookingStatus.BOOKED
    booking.checked_in_at = None
    booking.check_in_distance_meters = None
    booking.location_accuracy_meters = None
    booking.save(update_fields=["status", "checked_in_at", "check_in_distance_meters", "location_accuracy_meters", "updated_at"])
    return booking


@transaction.atomic
def cancel_booking(booking):
    Session.objects.select_for_update().get(pk=booking.session_id)
    booking = SessionBooking.objects.select_for_update().select_related("session").get(pk=booking.pk)
    if booking.status == BookingStatus.CANCELLED:
        return booking
    if booking.checked_in_at:
        raise ValidationError("A checked-in class booking cannot be cancelled.")
    was_booked = booking.status == BookingStatus.BOOKED
    booking.status = BookingStatus.CANCELLED
    booking.save(update_fields=["status", "updated_at"])
    if was_booked and booking.session.allow_waitlist and booking.session.capacity:
        next_booking = SessionBooking.objects.select_for_update().filter(
            session=booking.session, status=BookingStatus.WAITLISTED
        ).order_by("booked_at").first()
        if next_booking:
            next_booking.status = BookingStatus.BOOKED
            next_booking.save(update_fields=["status", "updated_at"])
    return booking


@transaction.atomic
def check_in_member(session_id, member, latitude=None, longitude=None, accuracy=None):
    session = Session.objects.select_for_update().get(pk=session_id)
    if session.status != SessionStatus.SCHEDULED or not session.attendance_required:
        raise ValidationError("Attendance is not available for this class.")
    if member.role != UserRole.STUDENT:
        raise PermissionDenied("Only member accounts can record class attendance.")
    booking = SessionBooking.objects.select_for_update().filter(
        session=session, member=member, status=BookingStatus.BOOKED
    ).first()
    if not booking and session.booking_required:
        raise PermissionDenied("Book this class before checking in.")
    if session.membership_required and not _member_has_active_membership(member).exists():
        raise PermissionDenied("An active membership is required to attend this class.")
    if session.course_id and session.course.effective_price > 0:
        from apps.enrollments.models import Enrollment
        enrollment = Enrollment.objects.filter(user=member, course=session.course).first()
        if not enrollment or not enrollment.is_active:
            raise PermissionDenied("Purchase or enroll in the linked course before attending this class.")
    if not booking:
        booked_count = SessionBooking.objects.filter(session=session, status=BookingStatus.BOOKED).count()
        if session.capacity and booked_count >= session.capacity:
            raise ValidationError("This class is full.")
        booking = SessionBooking.objects.create(session=session, member=member, status=BookingStatus.BOOKED)
    now = timezone.now()
    earliest = session.starts_at - timedelta(minutes=_config("check_in_early_minutes", 30))
    latest = session.ends_at + timedelta(minutes=_config("check_in_late_minutes", 20))
    if not (earliest <= now <= latest):
        raise ValidationError("Check-in is not open yet or the attendance window has closed.")
    if booking.checked_in_at:
        return booking

    distance = accuracy_value = None
    if _config("require_member_location", False):
        location = (session.latitude, session.longitude)
        if location[0] is None:
            location = (_config("attendance_latitude", None), _config("attendance_longitude", None))
        radius = session.geofence_radius_meters or _config("attendance_radius_meters", 150)
        distance, accuracy_value = _validate_location(latitude, longitude, accuracy, *location, radius)
    elif latitude not in (None, "") and longitude not in (None, ""):
        location = (session.latitude, session.longitude)
        if location[0] is None:
            location = (_config("attendance_latitude", None), _config("attendance_longitude", None))
        if location[0] is not None:
            distance, accuracy_value = _validate_location(
                latitude, longitude, accuracy, *location,
                session.geofence_radius_meters or _config("attendance_radius_meters", 150),
            )
    booking.checked_in_at = now
    booking.check_in_distance_meters = distance
    booking.location_accuracy_meters = accuracy_value
    booking.save(update_fields=["checked_in_at", "check_in_distance_meters", "location_accuracy_meters", "updated_at"])
    return booking


def can_clock_in(user):
    return user.is_authenticated and (user.role in (UserRole.EMPLOYEE, UserRole.TEACHER) or user.is_admin)


@transaction.atomic
def clock_in(user, latitude=None, longitude=None, accuracy=None, ip_address=None):
    if not can_clock_in(user):
        raise PermissionDenied("Employee or instructor access is required to use the time clock.")
    if not _config("allow_staff_check_in", True):
        raise PermissionDenied("Staff time-clock check-in is disabled by the administrator.")
    get_user_model().objects.select_for_update().only("pk").get(pk=user.pk)
    if StaffShift.objects.select_for_update().filter(employee=user, checked_out_at__isnull=True).exists():
        raise ValidationError("You already have an open shift. Check out before starting another one.")

    distance = accuracy_value = None
    if _config("require_staff_location", False):
        distance, accuracy_value = _validate_location(
            latitude, longitude, accuracy,
            _config("attendance_latitude", None),
            _config("attendance_longitude", None),
            _config("attendance_radius_meters", 150),
        )
    elif latitude not in (None, "") and longitude not in (None, ""):
        lat, lon, accuracy_value = _coordinate_pair(latitude, longitude, accuracy)
        target_lat = _config("attendance_latitude", None)
        target_lon = _config("attendance_longitude", None)
        if target_lat is not None and target_lon is not None:
            distance = distance_meters(lat, lon, target_lat, target_lon)

    return StaffShift.objects.create(
        employee=user,
        check_in_distance_meters=distance,
        check_in_accuracy_meters=accuracy_value,
        check_in_ip=ip_address,
    )


@transaction.atomic
def clock_out(user, latitude=None, longitude=None, accuracy=None, ip_address=None):
    if not can_clock_in(user):
        raise PermissionDenied("Employee or instructor access is required to use the time clock.")
    shift = StaffShift.objects.select_for_update().filter(employee=user, checked_out_at__isnull=True).first()
    if not shift:
        raise ValidationError("There is no open shift to check out of.")
    distance = accuracy_value = None
    if _config("require_staff_location", False):
        distance, accuracy_value = _validate_location(
            latitude, longitude, accuracy,
            _config("attendance_latitude", None),
            _config("attendance_longitude", None),
            _config("attendance_radius_meters", 150),
        )
    shift.checked_out_at = timezone.now()
    shift.check_out_distance_meters = distance
    shift.check_out_accuracy_meters = accuracy_value
    shift.check_out_ip = ip_address
    shift.save(update_fields=["checked_out_at", "check_out_distance_meters", "check_out_accuracy_meters", "check_out_ip", "updated_at"])
    return shift


def format_seconds_to_hm(seconds):
    """Convert a duration in seconds to a human-readable format like '1h 30m', '45m', or '0h 0m'."""
    sec = max(0, int(seconds))
    total_mins = sec // 60
    hours = total_mins // 60
    mins = total_mins % 60
    if hours > 0:
        return f"{hours}h {mins:02d}m"
    if mins > 0:
        return f"{mins}m"
    if sec > 0:
        return f"{sec}s"
    return "0h 0m"


def get_shift_statistics(shifts_queryset=None, employee=None):
    """
    Calculate total work hours and today's total work hours across staff shifts,
    with per-individual breakdown and login detail metrics.

    Args:
        shifts_queryset: Optional queryset to calculate from (defaults to StaffShift.objects.all()).
        employee: Optional User to filter by.

    Returns:
        dict containing:
            - total_seconds: integer sum of shift seconds
            - total_hours: float decimal hours rounded to 2 decimal places
            - formatted_total_hours: human-readable string (e.g. '8h 30m')
            - today_seconds: integer sum of today's shift seconds
            - today_hours: float decimal hours rounded to 2 decimal places
            - formatted_today_hours: human-readable string (e.g. '3h 15m')
            - open_shifts_count: number of currently active/open shifts
            - total_shifts_count: total shifts counted
            - today_shifts_count: total shifts recorded today
            - individual_stats: list of dicts for each employee with individual hours and login details
    """
    qs = shifts_queryset if shifts_queryset is not None else StaffShift.objects.select_related("employee").all()
    if employee is not None:
        qs = qs.filter(employee=employee)

    now = timezone.now()
    today_date = timezone.localdate(now)

    total_seconds = 0
    today_seconds = 0
    open_shifts_count = 0
    today_shifts_count = 0
    shifts_list = list(qs)

    # Group shifts by individual employee for per-person breakdown
    employee_shifts_map = {}

    for shift in shifts_list:
        dur = shift.duration_seconds
        total_seconds += dur
        if shift.is_open:
            open_shifts_count += 1

        # Check if the shift started today or finished today (or is open right now)
        shift_in_date = timezone.localdate(shift.checked_in_at)
        shift_out_date = timezone.localdate(shift.checked_out_at) if shift.checked_out_at else timezone.localdate(now)

        if shift_in_date == today_date or shift_out_date == today_date:
            today_seconds += dur
            today_shifts_count += 1

        # Accumulate for individual employee
        emp = shift.employee
        if emp.id not in employee_shifts_map:
            employee_shifts_map[emp.id] = {
                "employee": emp,
                "shifts": [],
            }
        employee_shifts_map[emp.id]["shifts"].append(shift)

    # If calculating platform-wide, also include staff/instructors without shifts yet
    if employee is None:
        from apps.accounts.models import UserRole
        User = get_user_model()
        staff_users = User.objects.filter(
            Q(role__in=[UserRole.EMPLOYEE, UserRole.TEACHER, UserRole.ADMIN]) | Q(staff_shifts__isnull=False)
        ).distinct()
        for u in staff_users:
            if u.id not in employee_shifts_map:
                employee_shifts_map[u.id] = {
                    "employee": u,
                    "shifts": [],
                }

    individual_stats = []
    for emp_id, data in employee_shifts_map.items():
        emp = data["employee"]
        emp_shifts = data["shifts"]
        emp_total_sec = 0
        emp_today_sec = 0
        emp_open_shift = None
        emp_today_count = 0
        latest_shift = None

        for s in emp_shifts:
            s_dur = s.duration_seconds
            emp_total_sec += s_dur
            if s.is_open and emp_open_shift is None:
                emp_open_shift = s
            s_in = timezone.localdate(s.checked_in_at)
            s_out = timezone.localdate(s.checked_out_at) if s.checked_out_at else timezone.localdate(now)
            if s_in == today_date or s_out == today_date:
                emp_today_sec += s_dur
                emp_today_count += 1
            if latest_shift is None:
                latest_shift = s

        name = getattr(emp, "full_name", "") or emp.get_full_name() if hasattr(emp, "get_full_name") else ""
        if not name:
            name = emp.email

        last_ip = (
            latest_shift.check_in_ip
            if latest_shift and latest_shift.check_in_ip
            else None
        )

        role_display = (
            emp.get_role_display()
            if hasattr(emp, "get_role_display")
            else str(getattr(emp, "role", "Staff")).capitalize()
        )

        individual_stats.append({
            "employee": emp,
            "user_id": str(emp.id),
            "name": name,
            "email": emp.email,
            "role": getattr(emp, "role", "employee"),
            "role_display": role_display,
            "last_login": emp.last_login,
            "today_seconds": emp_today_sec,
            "today_hours": round(emp_today_sec / 3600.0, 2),
            "formatted_today_hours": format_seconds_to_hm(emp_today_sec),
            "total_seconds": emp_total_sec,
            "total_hours": round(emp_total_sec / 3600.0, 2),
            "formatted_total_hours": format_seconds_to_hm(emp_total_sec),
            "is_on_shift": emp_open_shift is not None,
            "open_shift": emp_open_shift,
            "today_shifts_count": emp_today_count,
            "total_shifts_count": len(emp_shifts),
            "latest_shift": latest_shift,
            "last_ip": last_ip,
        })

    # Sort: active on-shift first, then by today's hours desc, then total hours desc, then name
    individual_stats.sort(
        key=lambda item: (
            not item["is_on_shift"],
            -item["today_seconds"],
            -item["total_seconds"],
            item["name"].lower(),
        )
    )

    return {
        "total_seconds": total_seconds,
        "total_hours": round(total_seconds / 3600.0, 2),
        "formatted_total_hours": format_seconds_to_hm(total_seconds),
        "today_seconds": today_seconds,
        "today_hours": round(today_seconds / 3600.0, 2),
        "formatted_today_hours": format_seconds_to_hm(today_seconds),
        "open_shifts_count": open_shifts_count,
        "total_shifts_count": len(shifts_list),
        "today_shifts_count": today_shifts_count,
        "individual_stats": individual_stats,
    }

