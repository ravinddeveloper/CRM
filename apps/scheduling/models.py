"""Bookable business sessions and auditable attendance records."""
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.common.models import BaseModel


class SessionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SCHEDULED = "scheduled", "Scheduled"
    CANCELLED = "cancelled", "Cancelled"
    COMPLETED = "completed", "Completed"


class SessionType(models.TextChoices):
    IN_PERSON = "in_person", "In person"
    LIVE_ONLINE = "live_online", "Live online"
    HYBRID = "hybrid", "Hybrid"
    APPOINTMENT = "appointment", "Appointment"


class BookingStatus(models.TextChoices):
    BOOKED = "booked", "Booked"
    WAITLISTED = "waitlisted", "Waitlisted"
    CANCELLED = "cancelled", "Cancelled"


class MembershipStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PAUSED = "paused", "Paused"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


class Session(BaseModel):
    """A scheduled class, workout, workshop, live stream, or appointment."""

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    session_type = models.CharField(max_length=20, choices=SessionType.choices, default=SessionType.IN_PERSON)
    status = models.CharField(max_length=20, choices=SessionStatus.choices, default=SessionStatus.SCHEDULED)
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField()
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_sessions",
        limit_choices_to=Q(role__in=["teacher", "employee", "admin"]),
    )
    course = models.ForeignKey(
        "courses.Course", on_delete=models.SET_NULL, null=True, blank=True, related_name="scheduled_sessions"
    )
    location_name = models.CharField(max_length=160, blank=True)
    address = models.TextField(blank=True)
    meeting_url = models.URLField(blank=True, help_text="Private meeting link shown only to booked members.")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geofence_radius_meters = models.PositiveIntegerField(null=True, blank=True)
    capacity = models.PositiveIntegerField(default=0, help_text="0 means unlimited.")
    booking_required = models.BooleanField(default=True)
    attendance_required = models.BooleanField(default=True)
    membership_required = models.BooleanField(default=False)
    allow_waitlist = models.BooleanField(default=True)

    class Meta:
        ordering = ["starts_at"]
        indexes = [
            models.Index(fields=["status", "starts_at"], name="session_status_start_idx"),
            models.Index(fields=["instructor", "starts_at"], name="session_instructor_start_idx"),
        ]
        constraints = [models.CheckConstraint(condition=Q(ends_at__gt=models.F("starts_at")), name="session_end_after_start")]

    def clean(self):
        super().clean()
        if (self.latitude is None) != (self.longitude is None):
            raise ValidationError("Set both location coordinates or leave both empty.")
        if self.latitude is not None and not (-90 <= self.latitude <= 90):
            raise ValidationError({"latitude": "Latitude must be between -90 and 90."})
        if self.longitude is not None and not (-180 <= self.longitude <= 180):
            raise ValidationError({"longitude": "Longitude must be between -180 and 180."})

    @property
    def seats_taken(self):
        return self.bookings.filter(status=BookingStatus.BOOKED).count()

    @property
    def is_open(self):
        return self.status == SessionStatus.SCHEDULED and self.ends_at > timezone.now()

    def __str__(self):
        return f"{self.title} ({self.starts_at:%Y-%m-%d %H:%M})"


class MembershipPlan(BaseModel):
    """A manually managed member plan suitable for gym or studio access."""

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    duration_days = models.PositiveIntegerField(null=True, blank=True, help_text="Leave blank for no expiry.")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="INR")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class MemberMembership(BaseModel):
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    plan = models.ForeignKey(MembershipPlan, on_delete=models.PROTECT, related_name="memberships")
    status = models.CharField(max_length=20, choices=MembershipStatus.choices, default=MembershipStatus.ACTIVE)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-starts_at"]
        indexes = [models.Index(fields=["member", "status", "ends_at"], name="membership_member_status_idx")]

    def save(self, *args, **kwargs):
        if self.plan_id and self.ends_at is None:
            duration_days = self.plan.duration_days
            if duration_days:
                self.ends_at = self.starts_at + timedelta(days=duration_days)
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        now = timezone.now()
        return self.status == MembershipStatus.ACTIVE and self.starts_at <= now and (self.ends_at is None or self.ends_at > now)

    def __str__(self):
        return f"{self.member} — {self.plan}"


class SessionBooking(BaseModel):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="bookings")
    member = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="session_bookings")
    status = models.CharField(max_length=20, choices=BookingStatus.choices, default=BookingStatus.BOOKED)
    booked_at = models.DateTimeField(auto_now_add=True)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    check_in_distance_meters = models.PositiveIntegerField(null=True, blank=True)
    location_accuracy_meters = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["booked_at"]
        constraints = [models.UniqueConstraint(fields=["session", "member"], name="unique_session_booking")]
        indexes = [
            models.Index(fields=["member", "status"], name="booking_member_status_idx"),
            models.Index(fields=["session", "status"], name="booking_session_status_idx"),
        ]

    def __str__(self):
        return f"{self.member} — {self.session} ({self.status})"


class StaffShift(BaseModel):
    """Employee time-clock record; raw device coordinates are deliberately not retained."""

    employee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="staff_shifts")
    checked_in_at = models.DateTimeField(default=timezone.now)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    check_in_distance_meters = models.PositiveIntegerField(null=True, blank=True)
    check_out_distance_meters = models.PositiveIntegerField(null=True, blank=True)
    check_in_accuracy_meters = models.PositiveIntegerField(null=True, blank=True)
    check_out_accuracy_meters = models.PositiveIntegerField(null=True, blank=True)
    check_in_ip = models.GenericIPAddressField(null=True, blank=True)
    check_out_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-checked_in_at"]
        indexes = [models.Index(fields=["employee", "checked_in_at"], name="shift_employee_time_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(checked_out_at__isnull=True) | Q(checked_out_at__gte=models.F("checked_in_at")),
                name="staff_shift_checkout_after_checkin",
            ),
            models.UniqueConstraint(
                fields=["employee"], condition=Q(checked_out_at__isnull=True), name="one_open_shift_per_employee"
            ),
        ]

    @property
    def is_open(self):
        return self.checked_out_at is None

    @property
    def duration_timedelta(self):
        end = self.checked_out_at or timezone.now()
        if end >= self.checked_in_at:
            return end - self.checked_in_at
        return timedelta(0)

    @property
    def duration_seconds(self):
        return int(self.duration_timedelta.total_seconds())

    @property
    def duration_hours(self):
        """Duration formatted as decimal hours (e.g., 2.5)."""
        return round(self.duration_seconds / 3600.0, 2)

    @property
    def formatted_duration(self):
        """Format duration into human-readable representation like '2h 15m' or '45s'."""
        sec = self.duration_seconds
        total_mins = sec // 60
        hours = total_mins // 60
        mins = total_mins % 60
        if hours > 0:
            return f"{hours}h {mins:02d}m"
        if mins > 0:
            return f"{mins}m"
        return f"{sec}s"

    def __str__(self):
        return f"{self.employee} — {self.checked_in_at:%Y-%m-%d %H:%M}"
