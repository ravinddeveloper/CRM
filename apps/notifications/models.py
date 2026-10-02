"""Notifications models."""
from django.contrib.auth import get_user_model
from django.db import models

from apps.common.models import BaseModel

User = get_user_model()


class NotificationType(models.TextChoices):
    PURCHASE = "purchase", "Purchase Confirmation"
    ENROLLMENT = "enrollment", "Enrollment"
    NEW_LECTURE = "new_lecture", "New Lecture"
    COURSE_UPDATE = "course_update", "Course Update"
    ANNOUNCEMENT = "announcement", "Announcement"
    PAYMENT_FAILED = "payment_failed", "Payment Failed"
    REFUND = "refund", "Refund"
    CERTIFICATE = "certificate", "Certificate"
    SYSTEM = "system", "System"


class Notification(BaseModel):
    """In-app notification for a user."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    notification_type = models.CharField(max_length=30, choices=NotificationType.choices)
    title = models.CharField(max_length=255)
    message = models.TextField()
    action_url = models.URLField(blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.notification_type}: {self.title} → {self.user.email}"

    def mark_read(self):
        from django.utils import timezone
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=["is_read", "read_at"])


class NotificationSyncEvent(models.Model):
    """Durable SQL outbox for synchronizing notifications into MongoDB."""
    UPSERT = "upsert"
    DELETE = "delete"
    EVENT_CHOICES = [(UPSERT, "Upsert"), (DELETE, "Delete")]

    event_type = models.CharField(max_length=10, choices=EVENT_CHOICES)
    notification_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["processed_at", "created_at"])]


class AnnouncementPriority(models.TextChoices):
    NORMAL = "normal", "Normal"
    IMPORTANT = "important", "Important"
    URGENT = "urgent", "Urgent"


class Announcement(BaseModel):
    """Platform-wide or course-specific announcements made by admins or teachers."""
    title = models.CharField(max_length=255)
    content = models.TextField()
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_announcements")
    course = models.ForeignKey(
        "courses.Course",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="announcements",
        help_text="Leave blank for platform-wide announcements; set course for course students only."
    )
    priority = models.CharField(
        max_length=20,
        choices=AnnouncementPriority.choices,
        default=AnnouncementPriority.NORMAL,
    )
    is_pinned = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]
        indexes = [
            models.Index(fields=["is_published", "is_pinned", "-created_at"]),
            models.Index(fields=["course", "is_published"]),
        ]

    def __str__(self):
        scope = f"[{self.course.title}]" if self.course else "[Platform]"
        return f"{scope} {self.title} by {self.author}"
