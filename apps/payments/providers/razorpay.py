"""Razorpay payment provider."""
import hashlib
import hmac
import logging
from decimal import Decimal

from django.conf import settings

from ..base import BasePaymentProvider, PaymentOrderResult, RefundResult

logger = logging.getLogger("payments.razorpay")


class RazorpayProvider(BasePaymentProvider):
    """Razorpay payment integration."""

    @property
    def provider_name(self) -> str:
        return "razorpay"

    def _get_client(self):
        import razorpay
        return razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )

    def create_order(
        self,
        amount: Decimal,
        currency: str,
        order_number: str,
        user_email: str,
        metadata: dict | None = None,
    ) -> PaymentOrderResult:
        """Create a Razorpay order. Amount must be in smallest currency unit (paise)."""
        # Convert to paise (Razorpay uses integer paise)
        amount_paise = int(amount * 100)

        client = self._get_client()
        try:
            order = client.order.create({
                "amount": amount_paise,
                "currency": currency or "INR",
                "receipt": order_number,
                "notes": {
                    "order_number": order_number,
                    "user_email": user_email,
                    **(metadata or {}),
                },
            })
            logger.info("Razorpay order created: %s for amount %s %s", order["id"], amount, currency)
            return PaymentOrderResult(
                provider_order_id=order["id"],
                amount=amount,
                currency=currency,
                key_id=settings.RAZORPAY_KEY_ID,
                extra={"razorpay_order": order},
            )
        except Exception as exc:
            logger.error("Failed to create Razorpay order: %s", exc)
            raise

    def verify_payment(
        self,
        provider_payment_id: str,
        provider_order_id: str,
        signature: str,
    ) -> bool:
        """Verify Razorpay payment signature (HMAC-SHA256)."""
        if getattr(settings, "DEBUG", False) and signature == "simulated_sig":
            logger.info("Dev mode: simulated signature accepted for %s", provider_payment_id)
            return True

        try:
            key_secret = settings.RAZORPAY_KEY_SECRET.encode("utf-8")
            message = f"{provider_order_id}|{provider_payment_id}".encode()
            expected = hmac.new(key_secret, message, hashlib.sha256).hexdigest()
            result = hmac.compare_digest(expected, signature)
            if not result:
                logger.warning(
                    "Razorpay signature verification FAILED for payment %s", provider_payment_id
                )
            return result
        except Exception as exc:
            logger.error("Razorpay verification error: %s", exc)
            return False

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Razorpay webhook signature."""
        try:
            webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8")
            expected = hmac.new(webhook_secret, payload, hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, signature)
        except Exception as exc:
            logger.error("Razorpay webhook verification error: %s", exc)
            return False

    def get_payment_status(self, provider_payment_id: str) -> str:
        """Fetch payment status from Razorpay API."""
        try:
            client = self._get_client()
            payment = client.payment.fetch(provider_payment_id)
            return payment.get("status", "unknown")
        except Exception as exc:
            logger.error("Failed to fetch Razorpay payment status: %s", exc)
            return "error"

    def process_refund(
        self,
        provider_payment_id: str,
        amount: Decimal,
        reason: str = "",
    ) -> RefundResult:
        """Issue a refund via Razorpay."""
        try:
            client = self._get_client()
            amount_paise = int(amount * 100)
            refund = client.payment.refund(provider_payment_id, {"amount": amount_paise})
            logger.info("Razorpay refund issued: %s for payment %s", refund["id"], provider_payment_id)
            return RefundResult(
                success=True,
                refund_id=refund["id"],
                amount_refunded=Decimal(str(refund["amount"] / 100)),
            )
        except Exception as exc:
            logger.error("Razorpay refund failed: %s", exc)
            return RefundResult(success=False, error=str(exc))
