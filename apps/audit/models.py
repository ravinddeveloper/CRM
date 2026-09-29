"""Audit log model."""
from django.contrib.auth import get_user_model
from django.db import models

from apps.common.models import BaseModel

User = get_user_model()


class AuditAction(models.TextChoices):
    USER_CREATED = "user_created", "User Created"
    USER_DELETED = "user_deleted", "User Deleted"
    USER_SUSPENDED = "user_suspended", "User Suspended"
    USER_ACTIVATED = "user_activated", "User Activated"
    USER_LOGIN = "user_login", "User Login"
    USER_LOGOUT = "user_logout", "User Logout"
    PASSWORD_RESET = "password_reset", "Password Reset"
    EMAIL_VERIFIED = "email_verified", "Email Verified"
    COURSE_CREATED = "course_created", "Course Created"
    COURSE_PUBLISHED = "course_published", "Course Published"
    COURSE_UNPUBLISHED = "course_unpublished", "Course Unpublished"
    COURSE_DELETED = "course_deleted", "Course Deleted"
    LECTURE_UPLOADED = "lecture_uploaded", "Lecture Uploaded"
    PRICE_CHANGED = "price_changed", "Price Changed"
    ORDER_CREATED = "order_created", "Order Created"
    PAYMENT_RECEIVED = "payment_received", "Payment Received"
    PAYMENT_FAILED = "payment_failed", "Payment Failed"
    REFUND_ISSUED = "refund_issued", "Refund Issued"
    ENROLLMENT_CREATED = "enrollment_created", "Enrollment Created"
    ENROLLMENT_REVOKED = "enrollment_revoked", "Enrollment Revoked"
    COUPON_CREATED = "coupon_created", "Coupon Created"
    ROLE_CHANGED = "role_changed", "Role Changed"
    SETTINGS_CHANGED = "settings_changed", "Settings Changed"
    FILE_UPLOADED = "file_uploaded", "File Uploaded"


class AuditLog(BaseModel):
    """Immutable audit trail of important actions."""
    actor = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="audit_logs"
    )
    action = models.CharField(max_length=50, choices=AuditAction.choices)
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=100, blank=True)
    object_repr = models.CharField(max_length=500, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["actor", "action"]),
            models.Index(fields=["action", "-created_at"]),
            models.Index(fields=["object_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.action} by {self.actor} at {self.created_at}"

    @classmethod
    def log(cls, action: str, actor=None, obj=None, ip=None, extra=None):
        """Convenience method to create audit log entries."""
        obj_type = ""
        obj_id = ""
        obj_repr = ""
        if obj:
            obj_type = obj.__class__.__name__
            obj_id = str(getattr(obj, "pk", ""))
            obj_repr = str(obj)[:500]

        return cls.objects.create(
            actor=actor,
            action=action,
            object_type=obj_type,
            object_id=obj_id,
            object_repr=obj_repr,
            ip_address=ip,
            extra=extra or {},
        )
