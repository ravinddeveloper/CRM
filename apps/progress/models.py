"""Progress models - CourseProgress, LectureProgress."""
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class CourseProgress(BaseModel):
    """Tracks a student's overall progress in an enrolled course."""
    enrollment = models.OneToOneField(
        "enrollments.Enrollment", on_delete=models.CASCADE, related_name="progress"
    )
    completion_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    completed_lectures = models.PositiveIntegerField(default=0)
    total_lectures = models.PositiveIntegerField(default=0)
    total_learning_time_seconds = models.PositiveIntegerField(default=0)
    last_accessed_lecture = models.ForeignKey(
        "lectures.Lecture", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Course Progress"
        verbose_name_plural = "Course Progresses"

    def __str__(self):
        return (
            f"{self.enrollment.user.email} / {self.enrollment.course.title} "
            f"({self.completion_percentage}%)"
        )

    @property
    def is_completed(self):
        return self.completion_percentage >= Decimal("100.00")

    def recalculate(self):
        """Recalculate completion from lecture progress records against actual total course lectures."""
        from apps.lectures.models import Lecture

        course = self.enrollment.course
        total = Lecture.objects.filter(
            section__course=course,
            is_published=True,
            section__is_published=True,
        ).count()
        if total == 0:
            total = Lecture.objects.filter(
                section__course=course,
                is_published=True,
            ).count()
        if total == 0:
            total = Lecture.objects.filter(section__course=course).count()
        if total == 0:
            total = self.lecture_progresses.count()

        completed = self.lecture_progresses.filter(
            is_completed=True,
            lecture__section__course=course,
            lecture__is_published=True,
        ).count()
        if completed == 0:
            completed = self.lecture_progresses.filter(is_completed=True).count()

        learning_time = (
            self.lecture_progresses.aggregate(
                total=models.Sum("watched_duration_seconds")
            )["total"] or 0
        )
        self.total_lectures = total
        self.completed_lectures = min(completed, total) if total > 0 else completed
        self.total_learning_time_seconds = learning_time
        if total > 0:
            pct = min(100.0, (completed / total) * 100)
            self.completion_percentage = Decimal(str(round(pct, 2)))
        else:
            self.completion_percentage = Decimal("0.00")

        from django.utils import timezone
        if self.completion_percentage >= 100:
            if not self.completed_at:
                self.completed_at = timezone.now()
            try:
                from apps.certificates.models import Certificate
                Certificate.objects.get_or_create(
                    enrollment=self.enrollment,
                    defaults={
                        "user": self.enrollment.user,
                        "course": course,
                        "completed_at": self.completed_at,
                    },
                )
            except Exception:
                pass
        elif self.completion_percentage < 100:
            self.completed_at = None

        self.save(update_fields=[
            "total_lectures", "completed_lectures", "total_learning_time_seconds",
            "completion_percentage", "completed_at"
        ])


class LectureProgress(BaseModel):
    """Tracks a student's progress within a specific lecture."""
    course_progress = models.ForeignKey(
        CourseProgress, on_delete=models.CASCADE, related_name="lecture_progresses"
    )
    lecture = models.ForeignKey(
        "lectures.Lecture", on_delete=models.CASCADE, related_name="progress_records"
    )
    is_started = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)

    # Video position tracking (in seconds)
    video_position_seconds = models.PositiveIntegerField(default=0)
    watched_duration_seconds = models.PositiveIntegerField(default=0)
    completion_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00")
    )

    # Timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_watched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("course_progress", "lecture")]
        indexes = [
            models.Index(fields=["course_progress", "is_completed"]),
        ]

    def __str__(self):
        return f"{self.lecture.title} — {self.completion_percentage}%"

    def update_position(self, position_seconds: int, watched_seconds: int, video_duration: int):
        """Update video position and check completion threshold."""
        from django.utils import timezone
        now = timezone.now()

        if not self.is_started:
            self.is_started = True
            self.started_at = now

        self.video_position_seconds = max(self.video_position_seconds, position_seconds)
        self.watched_duration_seconds = max(self.watched_duration_seconds, watched_seconds, position_seconds)
        self.last_watched_at = now

        # Calculate completion percentage
        if video_duration > 0:
            effective_watched = max(self.watched_duration_seconds, self.video_position_seconds)
            pct = min(100.0, (effective_watched / video_duration) * 100)
            self.completion_percentage = Decimal(str(round(pct, 2)))
        else:
            self.completion_percentage = Decimal("100.00")

        # Check completion threshold
        threshold = getattr(settings, "LECTURE_COMPLETION_THRESHOLD", 90)
        if self.completion_percentage >= threshold and not self.is_completed:
            self.is_completed = True
            self.completed_at = now

        self.save()
        # Propagate to parent
        self.course_progress.recalculate()


class StudentNote(BaseModel):
    """Personal notes taken or uploaded by a student for a lecture."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_notes"
    )
    lecture = models.ForeignKey(
        "lectures.Lecture", on_delete=models.CASCADE, related_name="student_notes"
    )
    course = models.ForeignKey(
        "courses.Course", on_delete=models.CASCADE, related_name="student_notes"
    )
    title = models.CharField(max_length=255, blank=True)
    content = models.TextField(blank=True, help_text="Personal notes typed by student")
    storage_key = models.CharField(
        max_length=500, blank=True, help_text="Storage key for uploaded note document"
    )
    original_filename = models.CharField(max_length=255, blank=True)
    file_size_bytes = models.PositiveBigIntegerField(default=0)
    video_timestamp_seconds = models.PositiveIntegerField(
        default=0, help_text="Timestamp in video when note was captured"
    )

    class Meta:
        verbose_name = "Student Note"
        verbose_name_plural = "Student Notes"
        ordering = ["video_timestamp_seconds", "-created_at"]
        indexes = [
            models.Index(fields=["user", "lecture"]),
            models.Index(fields=["user", "course"]),
        ]

    def __str__(self):
        return f"Note by {self.user.email} on {self.lecture.title}"

    @property
    def formatted_timestamp(self) -> str:
        """Returns MM:SS formatted timestamp string."""
        total_seconds = self.video_timestamp_seconds or 0
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"
