"""Accounts signals - auto-create profile on user creation."""
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a Profile when a new User is created."""
    if created:
        from .models import Profile
        Profile.objects.get_or_create(user=instance)


from datetime import timedelta
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.utils import timezone


@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    """Record user login details in audit log and track shift for employees."""
    ip = request.META.get("REMOTE_ADDR") if request else None
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:500] if request else ""

    # 1. Audit Log record
    try:
        from apps.audit.models import AuditAction, AuditLog
        AuditLog.log(
            action=AuditAction.USER_LOGIN,
            actor=user,
            ip=ip,
            extra={"user_agent": user_agent, "login_method": "password"},
        )
    except Exception:
        pass

    # 2. Staff shift tracking for staff/instructors based on login
    try:
        from apps.scheduling.models import StaffShift
        from apps.scheduling.services import can_clock_in
        if can_clock_in(user):
            now = timezone.now()
            # If user has an open shift from a previous day or older than 16 hours, close it
            open_shift = StaffShift.objects.filter(employee=user, checked_out_at__isnull=True).first()
            if open_shift:
                shift_date = timezone.localdate(open_shift.checked_in_at)
                today_date = timezone.localdate(now)
                if shift_date < today_date or (now - open_shift.checked_in_at).total_seconds() > 16 * 3600:
                    open_shift.checked_out_at = open_shift.checked_in_at + timedelta(hours=8)
                    open_shift.save(update_fields=["checked_out_at", "updated_at"])
                    open_shift = None
            if not open_shift:
                StaffShift.objects.create(
                    employee=user,
                    checked_in_at=now,
                    check_in_ip=ip,
                )
    except Exception:
        pass


@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs):
    """Record user logout in audit log and clock out staff shift."""
    ip = request.META.get("REMOTE_ADDR") if request else None

    # 1. Audit Log record
    if user and getattr(user, "is_authenticated", False):
        try:
            from apps.audit.models import AuditAction, AuditLog
            AuditLog.log(action=AuditAction.USER_LOGOUT, actor=user, ip=ip)
        except Exception:
            pass

        # 2. Close active staff shift upon logout
        try:
            from apps.scheduling.models import StaffShift
            from apps.scheduling.services import can_clock_in
            if can_clock_in(user):
                open_shift = StaffShift.objects.filter(employee=user, checked_out_at__isnull=True).first()
                if open_shift:
                    open_shift.checked_out_at = timezone.now()
                    open_shift.check_out_ip = ip
                    open_shift.save(update_fields=["checked_out_at", "check_out_ip", "updated_at"])
        except Exception:
            pass
