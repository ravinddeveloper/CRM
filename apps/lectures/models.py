"""Lectures models - Lecture, LectureVideo, LectureNote, Attachment."""
from django.db import models

from apps.common.models import BaseModel
from apps.courses.models import Section


class Lecture(BaseModel):
    """A single lecture inside a section."""
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="lectures")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_free_preview = models.BooleanField(
        default=False,
        help_text="If true, unenrolled students can view this lecture."
    )
    is_published = models.BooleanField(default=False)
    estimated_duration = models.PositiveIntegerField(default=0, help_text="Duration in seconds")

    class Meta:
        ordering = ["order"]
        indexes = [
            models.Index(fields=["section", "order"]),
            models.Index(fields=["is_published"]),
        ]

    def __str__(self):
        return f"{self.section.course.title} / {self.section.title} / {self.title}"

    @property
    def course(self):
        return self.section.course


class LectureVideo(BaseModel):
    """Video associated with a lecture. Stored in object storage, not on disk."""
    lecture = models.OneToOneField(Lecture, on_delete=models.CASCADE, related_name="video")
    storage_key = models.CharField(
        max_length=500,
        help_text="Key (path) in object storage bucket — NOT a public URL."
    )
    original_filename = models.CharField(max_length=255, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    file_size_bytes = models.PositiveBigIntegerField(default=0)
    mime_type = models.CharField(max_length=100, default="video/mp4")
    is_processed = models.BooleanField(default=True)
    thumbnail_key = models.CharField(max_length=500, blank=True)

    class Meta:
        verbose_name = "Lecture Video"

    def __str__(self):
        return f"Video: {self.lecture.title}"


class NoteType(models.TextChoices):
    HTML = "html", "HTML/Text"
    MARKDOWN = "markdown", "Markdown"
    PDF = "pdf", "PDF File"
    DOCX = "docx", "Word Document"
    OTHER = "other", "Other File"


class LectureNote(BaseModel):
    """Notes or documents attached to a lecture."""
    lecture = models.ForeignKey(Lecture, on_delete=models.CASCADE, related_name="notes")
    title = models.CharField(max_length=255)
    note_type = models.CharField(max_length=20, choices=NoteType.choices, default=NoteType.HTML)
    html_content = models.TextField(blank=True, help_text="For inline HTML/Markdown notes")
    storage_key = models.CharField(
        max_length=500, blank=True,
        help_text="For file-based notes stored in object storage."
    )
    original_filename = models.CharField(max_length=255, blank=True)
    file_size_bytes = models.PositiveBigIntegerField(default=0)
    mime_type = models.CharField(max_length=100, blank=True)
    is_downloadable = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Note: {self.title} ({self.lecture.title})"


class Attachment(BaseModel):
    """Additional file resource attached to a lecture."""
    lecture = models.ForeignKey(Lecture, on_delete=models.CASCADE, related_name="attachments")
    title = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=500)
    original_filename = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    file_size_bytes = models.PositiveBigIntegerField(default=0)
    is_downloadable = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Attachment: {self.title} ({self.lecture.title})"
