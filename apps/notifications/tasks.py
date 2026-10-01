"""Celery tasks for notifications and emails."""
import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger("apps.notifications")


def _branding():
    from apps.common.models import get_platform_settings
    from apps.common.theme import get_portal_colors

    settings_record = get_platform_settings()
    if isinstance(settings_record, dict):
        settings_record = {**settings_record, "portal_colors": get_portal_colors(settings_record)}
        return settings_record
    try:
        logo_url = settings_record.logo.url if settings_record.logo else ""
    except (ValueError, OSError):
        logo_url = ""
    return {
        "name": settings_record.name,
        "website_url": settings_record.website_url,
        "logo_url": logo_url,
        "portal_colors": get_portal_colors(settings_record),
    }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_verification_email(self, user_id: str):
    """Send email verification link to user."""
    try:
        from django.contrib.auth import get_user_model

        from apps.accounts.models import EmailVerificationToken
        User = get_user_model()
        user = User.objects.get(id=user_id)
        token = EmailVerificationToken.objects.filter(
            user=user, used_at__isnull=True
        ).order_by("-created_at").first()
        if not token:
            return

        branding = _branding()
        platform_name = branding["name"]
        verify_url = f"{branding.get('website_url') or settings.PLATFORM_URL}/accounts/verify-email/{token.token}/"
        html = render_to_string("emails/verify_email.html", {
            "user": user,
            "verify_url": verify_url,
            "platform_name": platform_name,
            "platform_logo_url": branding.get("logo_url", ""),
            "portal_colors": branding["portal_colors"],
        })
        send_mail(
            subject=f"Verify your email — {platform_name}",
            message=f"Click to verify: {verify_url}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html,
            fail_silently=False,
        )
        logger.info("Verification email sent to %s", user.email)
    except Exception as exc:
        logger.error("Failed to send verification email: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_reset_email(self, token_id: str):
    """Send password reset email."""
    try:
        from apps.accounts.models import PasswordResetToken
        token = PasswordResetToken.objects.select_related("user").get(id=token_id)
        branding = _branding()
        platform_name = branding["name"]
        reset_url = f"{branding.get('website_url') or settings.PLATFORM_URL}/accounts/reset-password/{token.token}/"
        html = render_to_string("emails/password_reset.html", {
            "user": token.user,
            "reset_url": reset_url,
            "platform_name": platform_name,
            "platform_logo_url": branding.get("logo_url", ""),
            "portal_colors": branding["portal_colors"],
        })
        send_mail(
            subject=f"Password Reset — {platform_name}",
            message=f"Reset your password: {reset_url}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[token.user.email],
            html_message=html,
            fail_silently=False,
        )
        logger.info("Password reset email sent to %s", token.user.email)
    except Exception as exc:
        logger.error("Failed to send password reset email: %s", exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_enrollment_email(self, order_id: str):
    """Send enrollment confirmation email."""
    try:
        from apps.orders.models import Order
        order = Order.objects.select_related("user").prefetch_related("items__course").get(id=order_id)
        branding = _branding()
        platform_name = branding["name"]
        html = render_to_string("emails/enrollment_confirmation.html", {
            "user": order.user,
            "order": order,
            "platform_name": platform_name,
            "platform_logo_url": branding.get("logo_url", ""),
            "portal_colors": branding["portal_colors"],
            "platform_url": branding.get("website_url") or settings.PLATFORM_URL,
        })
        send_mail(
            subject=f"You're enrolled! — {platform_name}",
            message=f"Order #{order.order_number} confirmed.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.user.email],
            html_message=html,
            fail_silently=False,
        )
        logger.info("Enrollment email sent for order %s", order.order_number)
    except Exception as exc:
        logger.error("Failed to send enrollment email: %s", exc)
        raise self.retry(exc=exc)
