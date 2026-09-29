"""Global template context processors."""
from django.conf import settings


def global_context(request):
    """Add global variables to all template contexts."""
    return {
        "PLATFORM_NAME": getattr(settings, "PLATFORM_NAME", "LearnPro"),
        "PLATFORM_URL": getattr(settings, "PLATFORM_URL", ""),
        "SUPPORT_EMAIL": getattr(settings, "SUPPORT_EMAIL", ""),
        "PAYMENT_PROVIDER": getattr(settings, "PAYMENT_PROVIDER", "razorpay"),
        "RAZORPAY_KEY_ID": getattr(settings, "RAZORPAY_KEY_ID", ""),
        "STRIPE_PUBLISHABLE_KEY": getattr(settings, "STRIPE_PUBLISHABLE_KEY", ""),
    }
