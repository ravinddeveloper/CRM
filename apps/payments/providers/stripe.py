"""Stripe payment provider."""
import logging
from decimal import Decimal

from django.conf import settings

from ..base import BasePaymentProvider, PaymentOrderResult, RefundResult

logger = logging.getLogger("payments.stripe")


class StripeProvider(BasePaymentProvider):
    """Stripe payment integration."""

    @property
    def provider_name(self) -> str:
        return "stripe"

    def create_order(
        self,
        amount: Decimal,
        currency: str,
        order_number: str,
        user_email: str,
        metadata: dict | None = None,
    ) -> PaymentOrderResult:
        """Create a Stripe PaymentIntent."""
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        amount_cents = int(amount * 100)

        try:
            intent = stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=(currency or "inr").lower(),
                receipt_email=user_email,
                metadata={
                    "order_number": order_number,
                    **(metadata or {}),
                },
            )
            logger.info("Stripe PaymentIntent created: %s", intent.id)
            return PaymentOrderResult(
                provider_order_id=intent.id,
                amount=amount,
                currency=currency,
                client_secret=intent.client_secret,
                extra={"payment_intent_id": intent.id},
            )
        except Exception as exc:
            logger.error("Failed to create Stripe PaymentIntent: %s", exc)
            raise

    def verify_payment(
        self,
        provider_payment_id: str,
        provider_order_id: str,
        signature: str,
    ) -> bool:
        """For Stripe, we verify via webhook. Direct verify just checks status."""
        try:
            import stripe
            stripe.api_key = settings.STRIPE_SECRET_KEY
            intent = stripe.PaymentIntent.retrieve(provider_order_id)
            return intent.status == "succeeded"
        except Exception as exc:
            logger.error("Stripe payment verification error: %s", exc)
            return False

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Stripe webhook signature."""
        import stripe
        try:
            stripe.Webhook.construct_event(
                payload, signature, settings.STRIPE_WEBHOOK_SECRET
            )
            return True
        except stripe.error.SignatureVerificationError:
            logger.warning("Stripe webhook signature verification failed")
            return False
        except Exception as exc:
            logger.error("Stripe webhook error: %s", exc)
            return False

    def get_payment_status(self, provider_payment_id: str) -> str:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            intent = stripe.PaymentIntent.retrieve(provider_payment_id)
            return intent.status
        except Exception as exc:
            logger.error("Failed to fetch Stripe payment status: %s", exc)
            return "error"

    def process_refund(
        self,
        provider_payment_id: str,
        amount: Decimal,
        reason: str = "",
    ) -> RefundResult:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            amount_cents = int(amount * 100)
            refund = stripe.Refund.create(
                payment_intent=provider_payment_id,
                amount=amount_cents,
            )
            logger.info("Stripe refund issued: %s", refund.id)
            return RefundResult(
                success=True,
                refund_id=refund.id,
                amount_refunded=Decimal(str(refund.amount / 100)),
            )
        except Exception as exc:
            logger.error("Stripe refund failed: %s", exc)
            return RefundResult(success=False, error=str(exc))
