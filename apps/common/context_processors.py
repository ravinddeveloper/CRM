"""Global template context processors."""
from django.conf import settings

from .models import get_platform_settings


def global_context(request):
    """Add global variables to all template contexts."""
    branding = get_platform_settings()

    def value(name, fallback=""):
        if isinstance(branding, dict):
            return branding.get(name, fallback)
        return getattr(branding, name, fallback)

    logo = value("logo")
    favicon = value("favicon")

    def file_url(field):
        try:
            return field.url if field else ""
        except (ValueError, OSError):
            return ""

    return {
        "PLATFORM_NAME": value("name", getattr(settings, "PLATFORM_NAME", "LearnPro")),
        "PLATFORM_TAGLINE": value("tagline"),
        "PLATFORM_LOGO_URL": file_url(logo),
        "PLATFORM_FAVICON_URL": file_url(favicon),
        "PLATFORM_PRIMARY_COLOR": value("primary_color", "#4f46e5"),
        "PLATFORM_URL": value("website_url", getattr(settings, "PLATFORM_URL", "")),
        "SUPPORT_EMAIL": value("support_email", getattr(settings, "SUPPORT_EMAIL", "")),
        "PAYMENT_PROVIDER": getattr(settings, "PAYMENT_PROVIDER", "razorpay"),
        "RAZORPAY_KEY_ID": getattr(settings, "RAZORPAY_KEY_ID", ""),
        "STRIPE_PUBLISHABLE_KEY": getattr(settings, "STRIPE_PUBLISHABLE_KEY", ""),
    }
