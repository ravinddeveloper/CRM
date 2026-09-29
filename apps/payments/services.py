"""Payment service - orchestrates checkout → payment → verification → enrollment."""
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order, OrderStatus

from .base import BasePaymentProvider
from .models import Payment, PaymentStatus, WebhookEvent

logger = logging.getLogger("payments")

_provider_cache = {}


def get_payment_provider(provider_name: str = None) -> BasePaymentProvider:
    """Return the configured payment provider instance."""
    name = provider_name or getattr(settings, "PAYMENT_PROVIDER", "razorpay")
    if name not in _provider_cache:
        if name == "razorpay":
            from .providers.razorpay import RazorpayProvider
            _provider_cache[name] = RazorpayProvider()
        elif name == "stripe":
            from .providers.stripe import StripeProvider
            _provider_cache[name] = StripeProvider()
        else:
            raise ValueError(f"Unknown payment provider: {name}")
    return _provider_cache[name]


class PaymentService:
    """Orchestrates the full payment lifecycle."""

    @staticmethod
    def initiate_checkout(order: Order) -> dict:
        """Create a payment order on the provider side. Returns data for frontend."""
        if order.status not in [OrderStatus.PENDING, OrderStatus.PAYMENT_INITIATED]:
            raise ValueError(f"Order {order.order_number} is not in a payable state.")

        provider = get_payment_provider()
        result = provider.create_order(
            amount=order.total,
            currency=order.currency,
            order_number=order.order_number,
            user_email=order.billing_email or order.user.email,
        )

        # Update order with provider reference
        order.payment_provider = provider.provider_name
        order.payment_provider_order_id = result.provider_order_id
        order.status = OrderStatus.PAYMENT_INITIATED
        order.save(update_fields=["payment_provider", "payment_provider_order_id", "status", "updated_at"])

        logger.info("Checkout initiated: order=%s provider=%s", order.order_number, provider.provider_name)

        return {
            "order_id": str(order.id),
            "order_number": order.order_number,
            "provider": provider.provider_name,
            "provider_order_id": result.provider_order_id,
            "amount": str(order.total),
            "currency": order.currency,
            "client_secret": result.client_secret,
            "key_id": result.key_id,
        }

    @staticmethod
    @transaction.atomic
    def verify_and_complete_payment(
        order: Order,
        provider_payment_id: str,
        provider_order_id: str,
        signature: str,
    ) -> Payment:
        """
        Verify payment signature server-side and create enrollment.
        NEVER called based on frontend-only payment status.
        """
        provider = get_payment_provider(order.payment_provider)

        # Verify signature
        is_valid = provider.verify_payment(provider_payment_id, provider_order_id, signature)
        if not is_valid:
            logger.warning(
                "Payment verification FAILED: order=%s payment=%s",
                order.order_number, provider_payment_id
            )
            PaymentService._record_payment(
                order, provider.provider_name, provider_payment_id, provider_order_id,
                signature, status=PaymentStatus.FAILED, error="Signature verification failed"
            )
            raise ValueError("Payment verification failed.")

        # Idempotency check - don't re-process an already-completed payment
        existing = Payment.objects.filter(
            provider=provider.provider_name,
            provider_payment_id=provider_payment_id,
            status=PaymentStatus.CAPTURED,
        ).first()
        if existing:
            logger.info("Duplicate payment callback ignored: %s", provider_payment_id)
            return existing

        # Record the successful payment
        payment = PaymentService._record_payment(
            order, provider.provider_name, provider_payment_id, provider_order_id,
            signature, status=PaymentStatus.CAPTURED,
        )

        # Complete the order
        order.payment_transaction_id = provider_payment_id
        order.status = OrderStatus.COMPLETED
        order.save(update_fields=["payment_transaction_id", "status", "updated_at"])

        # Create enrollments
        from apps.enrollments.services import EnrollmentService
        EnrollmentService.enroll_from_order(order)

        # Generate invoice (async)
        from apps.payments.tasks import (
            generate_invoice_task,
            send_payment_success_email,
        )
        generate_invoice_task.delay(str(order.id))
        send_payment_success_email.delay(str(order.id))

        logger.info(
            "Payment completed: order=%s payment=%s", order.order_number, provider_payment_id
        )
        return payment

    @staticmethod
    def _record_payment(
        order, provider, provider_payment_id, provider_order_id, signature,
        status, error=""
    ) -> Payment:
        """Create or update a Payment record."""
        payment, created = Payment.objects.get_or_create(
            provider=provider,
            provider_payment_id=provider_payment_id,
            defaults={
                "order": order,
                "provider_order_id": provider_order_id,
                "amount": order.total,
                "currency": order.currency,
                "status": status,
                "signature": signature,
                "error_message": error,
            },
        )
        if not created:
            payment.status = status
            payment.error_message = error
            payment.save(update_fields=["status", "error_message", "updated_at"])
        return payment

    @staticmethod
    @transaction.atomic
    def process_webhook(provider_name: str, payload: bytes, signature: str) -> None:
        """Process an incoming webhook. Idempotent."""
        import json
        provider = get_payment_provider(provider_name)

        # Verify webhook signature first
        if not provider.verify_webhook_signature(payload, signature):
            logger.warning("Webhook signature verification failed for %s", provider_name)
            raise ValueError("Invalid webhook signature.")

        data = json.loads(payload)

        # Extract event ID (provider-specific)
        if provider_name == "razorpay":
            event_id = data.get("payload", {}).get("payment", {}).get("entity", {}).get("id", "")
            event_type = data.get("event", "")
        elif provider_name == "stripe":
            event_id = data.get("id", "")
            event_type = data.get("type", "")
        else:
            event_id = str(data)[:100]
            event_type = "unknown"

        # Idempotency: skip if already processed
        webhook_event, created = WebhookEvent.objects.get_or_create(
            provider=provider_name,
            event_id=event_id,
            defaults={"event_type": event_type, "payload": data},
        )

        if not created and webhook_event.processed:
            logger.info("Duplicate webhook %s/%s ignored", provider_name, event_id)
            return

        # Process based on event type
        try:
            if "payment.captured" in event_type or "payment_intent.succeeded" in event_type:
                PaymentService._handle_payment_success_webhook(provider_name, data)

            webhook_event.processed = True
            webhook_event.processed_at = timezone.now()
            webhook_event.save(update_fields=["processed", "processed_at"])
        except Exception as exc:
            webhook_event.processing_error = str(exc)
            webhook_event.save(update_fields=["processing_error"])
            logger.error("Webhook processing error: %s", exc)
            raise

    @staticmethod
    def _handle_payment_success_webhook(provider_name: str, data: dict) -> None:
        """Handle a payment success webhook event."""
        if provider_name == "razorpay":
            entity = data.get("payload", {}).get("payment", {}).get("entity", {})
            provider_payment_id = entity.get("id")
            provider_order_id = entity.get("order_id")
        elif provider_name == "stripe":
            obj = data.get("data", {}).get("object", {})
            provider_payment_id = obj.get("id")
            provider_order_id = obj.get("id")
        else:
            return

        if not provider_payment_id:
            return

        # Find the order via provider order ID
        order = Order.objects.filter(
            payment_provider_order_id=provider_order_id
        ).select_for_update().first()

        if not order:
            logger.warning("Webhook: no order found for provider order %s", provider_order_id)
            return

        if order.status == OrderStatus.COMPLETED:
            logger.info("Webhook: order %s already completed", order.order_number)
            return

        # Mark payment and order
        Payment.objects.update_or_create(
            provider=provider_name,
            provider_payment_id=provider_payment_id,
            defaults={
                "order": order,
                "provider_order_id": provider_order_id,
                "amount": order.total,
                "currency": order.currency,
                "status": PaymentStatus.CAPTURED,
                "raw_response": data,
            },
        )

        order.payment_transaction_id = provider_payment_id
        order.status = OrderStatus.COMPLETED
        order.save(update_fields=["payment_transaction_id", "status", "updated_at"])

        from apps.enrollments.services import EnrollmentService
        EnrollmentService.enroll_from_order(order)

        from apps.payments.tasks import (
            generate_invoice_task,
            send_payment_success_email,
        )
        generate_invoice_task.delay(str(order.id))
        send_payment_success_email.delay(str(order.id))
