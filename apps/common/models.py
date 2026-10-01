"""Base models shared across all apps."""
import uuid

from django.core.validators import RegexValidator
from django.db import models


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
    primary_color = models.CharField(
        max_length=7,
        default="#4f46e5",
        validators=[RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Enter a six-digit hex color such as #4f46e5.")],
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "platform settings"
        verbose_name_plural = "platform settings"

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
        }
    try:
        cache.set(cache_key, value, 300)
    except Exception:
        pass
    return value
