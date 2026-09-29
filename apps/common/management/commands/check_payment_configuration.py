"""Management command to validate payment gateway configuration."""
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Check and validate payment provider credentials and webhook secrets."

    def handle(self, *args, **options):
        provider = getattr(settings, "PAYMENT_PROVIDER", "razorpay")
        self.stdout.write(f"Active Payment Gateway: '{provider}'\n")

        # Check Razorpay
        rzp_key = getattr(settings, "RAZORPAY_KEY_ID", "")
        rzp_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "")
        rzp_webhook = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")

        self.stdout.write("Checking Razorpay configuration:")
        if rzp_key:
            self.stdout.write(self.style.SUCCESS(f"  [OK] RAZORPAY_KEY_ID: {rzp_key[:6]}..."))
        else:
            self.stdout.write(self.style.WARNING("  [!] RAZORPAY_KEY_ID is not configured."))

        if rzp_secret:
            self.stdout.write(self.style.SUCCESS("  [OK] RAZORPAY_KEY_SECRET: [configured]"))
        else:
            self.stdout.write(self.style.WARNING("  [!] RAZORPAY_KEY_SECRET is not configured."))

        if rzp_webhook:
            self.stdout.write(self.style.SUCCESS("  [OK] RAZORPAY_WEBHOOK_SECRET: [configured]"))
        else:
            self.stdout.write(self.style.WARNING("  [!] RAZORPAY_WEBHOOK_SECRET is not configured."))

        # Check Stripe
        stripe_key = getattr(settings, "STRIPE_SECRET_KEY", "")
        stripe_webhook = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")

        self.stdout.write("\nChecking Stripe configuration:")
        if stripe_key:
            self.stdout.write(self.style.SUCCESS("  [OK] STRIPE_SECRET_KEY: [configured]"))
        else:
            self.stdout.write(self.style.WARNING("  [!] STRIPE_SECRET_KEY is not configured."))

        if stripe_webhook:
            self.stdout.write(self.style.SUCCESS("  [OK] STRIPE_WEBHOOK_SECRET: [configured]"))
        else:
            self.stdout.write(self.style.WARNING("  [!] STRIPE_WEBHOOK_SECRET is not configured."))

        self.stdout.write(self.style.SUCCESS("\nPayment configuration scan complete."))
