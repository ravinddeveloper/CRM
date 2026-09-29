"""Celery tasks for payments - invoice generation, emails."""
import logging

from celery import shared_task

logger = logging.getLogger("payments")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def generate_invoice_task(self, order_id: str):
    """Generate a PDF invoice for a completed order."""
    try:

        from apps.orders.models import Order
        from apps.payments.models import Invoice

        order = Order.objects.select_related("user").prefetch_related("items__course").get(id=order_id)

        # Idempotency check
        if hasattr(order, "invoice"):
            logger.info("Invoice already exists for order %s", order.order_number)
            return

        invoice = Invoice.objects.create(
            order=order,
            total=order.total,
            tax_amount=order.tax_amount,
            currency=order.currency,
        )
        invoice.invoice_number = invoice.generate_invoice_number()
        invoice.save(update_fields=["invoice_number"])

        # Generate PDF and store
        from apps.payments.invoice_service import InvoiceService
        InvoiceService.generate_pdf(invoice)

        logger.info("Invoice %s generated for order %s", invoice.invoice_number, order.order_number)
    except Exception as exc:
        logger.error("Invoice generation failed for order %s: %s", order_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_payment_success_email(self, order_id: str):
    """Send payment confirmation email to student."""
    try:
        from apps.notifications.tasks import send_enrollment_email
        send_enrollment_email(order_id)
    except Exception as exc:
        logger.error("Payment success email failed: %s", exc)
        raise self.retry(exc=exc)
