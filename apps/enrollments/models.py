"""Enrollments models."""
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel

User = get_user_model()


class EnrollmentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    EXPIRED = "expired", "Expired"
    SUSPENDED = "suspended", "Suspended"
    REVOKED = "revoked", "Revoked"


class AccessType(models.TextChoices):
    LIFETIME = "lifetime", "Lifetime Access"
    FIXED_DURATION = "fixed_duration", "Fixed Duration"
    SUBSCRIPTION = "subscription", "Subscription"


class Enrollment(BaseModel):
    """Grants a student access to a course."""
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="enrollments")
    course = models.ForeignKey("courses.Course", on_delete=models.PROTECT, related_name="enrollments")
    order = models.ForeignKey(
        "orders.Order", on_delete=models.PROTECT, null=True, blank=True,
        related_name="enrollments", help_text="Order that created this enrollment"
    )
    status = models.CharField(max_length=20, choices=EnrollmentStatus.choices, default=EnrollmentStatus.ACTIVE)
    access_type = models.CharField(max_length=20, choices=AccessType.choices, default=AccessType.LIFETIME)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("user", "course")]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["course", "status"]),
        ]

    def __str__(self):
        return f"{self.user.email} enrolled in {self.course.title}"

    @property
    def is_active(self):
        """Authoritative check: is this enrollment currently valid?"""
        if self.status != EnrollmentStatus.ACTIVE:
            return False
        if self.access_type == AccessType.LIFETIME:
            return True
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True

    def expire(self):
        self.status = EnrollmentStatus.EXPIRED
        self.save(update_fields=["status"])

    def revoke(self):
        self.status = EnrollmentStatus.REVOKED
        self.save(update_fields=["status"])
