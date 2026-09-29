"""Certificates models."""
import uuid

from django.contrib.auth import get_user_model
from django.db import models

from apps.common.models import BaseModel

User = get_user_model()


class Certificate(BaseModel):
    """Course completion certificate."""
    certificate_number = models.CharField(max_length=50, unique=True)
    enrollment = models.OneToOneField(
        "enrollments.Enrollment", on_delete=models.CASCADE, related_name="certificate"
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="certificates")
    course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="certificates")
    completed_at = models.DateTimeField()
    issued_at = models.DateTimeField(auto_now_add=True)
    storage_key = models.CharField(max_length=500, blank=True, help_text="PDF in object storage")
    verification_code = models.UUIDField(default=uuid.uuid4, unique=True)

    class Meta:
        ordering = ["-issued_at"]
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["verification_code"]),
        ]

    def __str__(self):
        return f"Certificate #{self.certificate_number} — {self.user.email}"

    def generate_certificate_number(self):
        from django.utils import timezone
        now = timezone.now()
        return f"CERT-{now.year}-{str(self.id)[:8].upper()}"

    def save(self, *args, **kwargs):
        if not self.certificate_number:
            if not self.id:
                self.id = uuid.uuid4()
            self.certificate_number = self.generate_certificate_number()
        super().save(*args, **kwargs)

    @property
    def verification_url(self):
        from django.conf import settings
        return f"{settings.PLATFORM_URL}/certificates/verify/{self.verification_code}/"
