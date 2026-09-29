"""Reviews models."""
from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import BaseModel

User = get_user_model()


class Review(BaseModel):
    """Course review by an enrolled student."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reviews")
    course = models.ForeignKey("courses.Course", on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    is_approved = models.BooleanField(default=True, help_text="Admins can unapprove reviews.")
    is_hidden = models.BooleanField(default=False)

    class Meta:
        unique_together = [("user", "course")]
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["course", "is_approved"])]

    def __str__(self):
        return f"{self.user.email} → {self.course.title} ({self.rating}/5)"
