"""Analytics models."""
from django.contrib.auth import get_user_model
from django.db import models

from apps.common.models import BaseModel

User = get_user_model()


class CourseView(BaseModel):
    """Records each course page view for analytics."""
    course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="views")
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    session_key = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["course", "created_at"])]

    def __str__(self):
        return f"View of {self.course.title}"


class DailyAnalytics(BaseModel):
    """Aggregated daily analytics snapshot."""
    date = models.DateField(unique=True)
    new_users = models.PositiveIntegerField(default=0)
    new_enrollments = models.PositiveIntegerField(default=0)
    completed_lectures = models.PositiveIntegerField(default=0)
    revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_orders = models.PositiveIntegerField(default=0)
    successful_orders = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"Daily Analytics {self.date}"
