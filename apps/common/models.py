"""Base models shared across all apps."""
import uuid

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

HEX_COLOR_VALIDATOR = RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Enter a six-digit hex color such as #4f46e5.")


class TimeStampedModel(models.Model):
    """Abstract base model with created_at and updated_at timestamps."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """Abstract base model with UUID primary key."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    """Abstract base combining UUID pk + timestamps."""

    class Meta:
        abstract = True


class BusinessType(models.TextChoices):
    LEARNING = "learning", "Learning and courses"
    DANCE = "dance", "Dance studio"
    FITNESS = "fitness", "Fitness classes"
    GYM = "gym", "Gym and membership"
    STUDIO = "studio", "Studio and workshops"
    COACHING = "coaching", "Coaching"
    OTHER = "other", "Other service business"


class PlatformSettings(models.Model):
    """Editable public identity and billing details for this LMS instance."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    name = models.CharField(max_length=120, default="LearnPro")
    tagline = models.CharField(max_length=200, blank=True, default="")
    logo = models.ImageField(upload_to="branding/", blank=True)
    favicon = models.ImageField(upload_to="branding/", blank=True)
    support_email = models.EmailField(blank=True)
    website_url = models.URLField(blank=True)
    legal_name = models.CharField(max_length=180, blank=True)
    billing_address = models.TextField(blank=True)
    tax_registration_number = models.CharField(max_length=80, blank=True)
    invoice_footer = models.CharField(max_length=240, blank=True)
    business_type = models.CharField(max_length=24, choices=BusinessType.choices, default=BusinessType.LEARNING)
    member_label = models.CharField(max_length=48, default="Student")
    staff_label = models.CharField(max_length=48, default="Teacher")
    class_label = models.CharField(max_length=48, default="Class")
    schedule_label = models.CharField(max_length=48, default="Schedule")
    allow_staff_check_in = models.BooleanField(default=True)
    require_staff_location = models.BooleanField(default=False)
    require_member_location = models.BooleanField(default=False)
    attendance_radius_meters = models.PositiveIntegerField(default=150)
    max_location_accuracy_meters = models.PositiveIntegerField(default=150)
    attendance_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    attendance_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    check_in_early_minutes = models.PositiveSmallIntegerField(default=30)
    check_in_late_minutes = models.PositiveSmallIntegerField(default=20)
    primary_color = models.CharField(
        max_length=7,
        default="#4f46e5",
        validators=[HEX_COLOR_VALIDATOR],
    )
    accent_color = models.CharField(max_length=7, default="#7c3aed", validators=[HEX_COLOR_VALIDATOR])
    background_color = models.CharField(max_length=7, default="#030712", validators=[HEX_COLOR_VALIDATOR])
    surface_color = models.CharField(max_length=7, default="#111827", validators=[HEX_COLOR_VALIDATOR])
    raised_surface_color = models.CharField(max_length=7, default="#1f2937", validators=[HEX_COLOR_VALIDATOR])
    text_color = models.CharField(max_length=7, default="#f9fafb", validators=[HEX_COLOR_VALIDATOR])
    muted_text_color = models.CharField(max_length=7, default="#9ca3af", validators=[HEX_COLOR_VALIDATOR])
    border_color = models.CharField(max_length=7, default="#374151", validators=[HEX_COLOR_VALIDATOR])
    inverse_text_color = models.CharField(max_length=7, default="#ffffff", validators=[HEX_COLOR_VALIDATOR])
    success_color = models.CharField(max_length=7, default="#10b981", validators=[HEX_COLOR_VALIDATOR])
    warning_color = models.CharField(max_length=7, default="#f59e0b", validators=[HEX_COLOR_VALIDATOR])
    error_color = models.CharField(max_length=7, default="#ef4444", validators=[HEX_COLOR_VALIDATOR])
    info_color = models.CharField(max_length=7, default="#3b82f6", validators=[HEX_COLOR_VALIDATOR])
    invoice_background_color = models.CharField(max_length=7, default="#ffffff", validators=[HEX_COLOR_VALIDATOR])
    invoice_surface_color = models.CharField(max_length=7, default="#f8fafc", validators=[HEX_COLOR_VALIDATOR])
    invoice_text_color = models.CharField(max_length=7, default="#1e293b", validators=[HEX_COLOR_VALIDATOR])
    invoice_muted_text_color = models.CharField(max_length=7, default="#64748b", validators=[HEX_COLOR_VALIDATOR])
    invoice_border_color = models.CharField(max_length=7, default="#e2e8f0", validators=[HEX_COLOR_VALIDATOR])
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "platform settings"
        verbose_name_plural = "platform settings"

    def clean(self):
        super().clean()
        if (self.attendance_latitude is None) != (self.attendance_longitude is None):
            raise ValidationError("Set both business attendance coordinates or leave both empty.")
        if self.attendance_latitude is not None and not (-90 <= self.attendance_latitude <= 90):
            raise ValidationError({"attendance_latitude": "Latitude must be between -90 and 90."})
        if self.attendance_longitude is not None and not (-180 <= self.attendance_longitude <= 180):
            raise ValidationError({"attendance_longitude": "Longitude must be between -180 and 180."})

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Keep one stable record; admins can clear individual values instead.
        return None

    def __str__(self):
        return self.name


def get_platform_settings():
    """Return the singleton settings, falling back safely before migrations."""
    from django.conf import settings
    from django.core.cache import cache

    cache_key = "common.platform_settings"
    try:
        value = cache.get(cache_key)
        if value is not None:
            return value
    except Exception:
        pass

    try:
        value = PlatformSettings.objects.filter(pk=1).first()
    except Exception:
        value = None
    if value is None:
        value = {
            "name": getattr(settings, "PLATFORM_NAME", "LearnPro"),
            "tagline": "",
            "logo": None,
            "favicon": None,
            "support_email": getattr(settings, "SUPPORT_EMAIL", ""),
            "website_url": getattr(settings, "PLATFORM_URL", ""),
            "legal_name": "",
            "billing_address": "",
            "tax_registration_number": "",
            "invoice_footer": "",
            "primary_color": "#4f46e5",
            "accent_color": "#7c3aed",
            "background_color": "#030712",
            "surface_color": "#111827",
            "raised_surface_color": "#1f2937",
            "text_color": "#f9fafb",
            "muted_text_color": "#9ca3af",
            "border_color": "#374151",
            "inverse_text_color": "#ffffff",
            "success_color": "#10b981",
            "warning_color": "#f59e0b",
            "error_color": "#ef4444",
            "info_color": "#3b82f6",
            "business_type": BusinessType.LEARNING,
            "member_label": "Student",
            "staff_label": "Teacher",
            "class_label": "Class",
            "schedule_label": "Schedule",
            "allow_staff_check_in": True,
            "require_staff_location": False,
            "require_member_location": False,
            "attendance_radius_meters": 150,
            "max_location_accuracy_meters": 150,
            "attendance_latitude": None,
            "attendance_longitude": None,
            "check_in_early_minutes": 30,
            "check_in_late_minutes": 20,
        }
    try:
        cache.set(cache_key, value, 300)
    except Exception:
        pass
    return value
