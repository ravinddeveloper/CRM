"""Courses models - Category, Course, Section, Tag."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.common.models import BaseModel

User = get_user_model()


class Category(BaseModel):
    """Course category (supports nesting)."""
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="subcategories",
    )
    icon = models.CharField(max_length=80, blank=True, help_text="CSS icon class or emoji")
    image = models.ImageField(upload_to="categories/", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"
        ordering = ["order", "name"]
        indexes = [models.Index(fields=["slug"])]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Tag(BaseModel):
    """Course tags for search and filtering."""
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class CourseStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"
    UNDER_REVIEW = "under_review", "Under Review"


class DifficultyLevel(models.TextChoices):
    BEGINNER = "beginner", "Beginner"
    INTERMEDIATE = "intermediate", "Intermediate"
    ADVANCED = "advanced", "Advanced"
    EXPERT = "expert", "Expert"


class Course(BaseModel):
    """Main course model."""
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=300, unique=True)
    short_description = models.TextField(max_length=500)
    description = models.TextField()
    thumbnail = models.ImageField(upload_to="courses/thumbnails/", null=True, blank=True)
    preview_video_key = models.CharField(
        max_length=500, blank=True,
        help_text="Storage key for a free preview video"
    )

    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="courses"
    )
    teacher = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="courses", limit_choices_to={"role": "teacher"}
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="courses")

    # Pricing
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    discount_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="If set, this is the current selling price."
    )
    currency = models.CharField(max_length=3, default="INR")
    is_free = models.BooleanField(default=False)

    # Status
    status = models.CharField(max_length=20, choices=CourseStatus.choices, default=CourseStatus.DRAFT)
    is_featured = models.BooleanField(default=False)
    is_bestseller = models.BooleanField(default=False)

    # Content metadata
    difficulty = models.CharField(
        max_length=20, choices=DifficultyLevel.choices, default=DifficultyLevel.BEGINNER
    )
    language = models.CharField(max_length=50, default="English")
    estimated_duration = models.PositiveIntegerField(
        default=0, help_text="Estimated total duration in minutes"
    )
    learning_objectives = models.JSONField(default=list, blank=True)
    requirements = models.JSONField(default=list, blank=True)

    # Timestamps
    published_at = models.DateTimeField(null=True, blank=True)

    # Analytics cache
    enrollment_count = models.PositiveIntegerField(default=0)
    review_count = models.PositiveIntegerField(default=0)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal("0.00"))
    total_views = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Course"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "teacher"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["is_featured", "status"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Course.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def effective_price(self):
        """Return the actual price students pay."""
        if self.is_free:
            return Decimal("0.00")
        if self.discount_price is not None:
            return self.discount_price
        return self.price

    @property
    def discount_percentage(self):
        if self.discount_price and self.price > 0:
            savings = self.price - self.discount_price
            return int((savings / self.price) * 100)
        return 0

    @property
    def is_published(self):
        return self.status == CourseStatus.PUBLISHED

    def publish(self):
        self.status = CourseStatus.PUBLISHED
        if not self.published_at:
            self.published_at = timezone.now()
        self.save(update_fields=["status", "published_at"])

    def unpublish(self):
        self.status = CourseStatus.DRAFT
        self.save(update_fields=["status"])

    def get_total_lectures(self):
        return sum(section.lectures.filter(is_published=True).count() for section in self.sections.all())

    @property
    def total_lectures_count(self):
        from apps.lectures.models import Lecture
        return Lecture.objects.filter(section__course=self, is_published=True).count()

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("marketplace:course_detail", kwargs={"slug": self.slug})


class Section(BaseModel):
    """A module/chapter within a course."""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="sections")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]
        indexes = [models.Index(fields=["course", "order"])]

    def __str__(self):
        return f"{self.course.title} - {self.title}"
