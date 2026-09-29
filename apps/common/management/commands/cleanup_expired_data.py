"""Management command to clean up expired data."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import EmailVerificationToken, PasswordResetToken
from apps.payments.models import WebhookEvent


class Command(BaseCommand):
    help = "Cleanup expired email verification tokens, password resets, and old webhook logs."

    def handle(self, *args, **options):
        now = timezone.now()

        # 1. Expired email verifications
        del_verif, _ = EmailVerificationToken.objects.filter(expires_at__lt=now).delete()
        self.stdout.write(f"Removed {del_verif} expired email verification records.")

        # 2. Expired password resets
        del_reset, _ = PasswordResetToken.objects.filter(expires_at__lt=now).delete()
        self.stdout.write(f"Removed {del_reset} expired password reset records.")

        # 3. Old processed webhook events (older than 30 days)
        cutoff = now - timedelta(days=30)
        del_webhooks, _ = WebhookEvent.objects.filter(processed=True, processed_at__lt=cutoff).delete()
        self.stdout.write(f"Removed {del_webhooks} old webhook event records.")

        self.stdout.write(self.style.SUCCESS("Cleanup completed successfully."))
