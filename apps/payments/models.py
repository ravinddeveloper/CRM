"""Payments models - Payment, WebhookEvent, Invoice."""
from decimal import Decimal

from django.db import models

from apps.common.models import BaseModel


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    INITIATED = "initiated", "Initiated"
    AUTHORIZED = "authorized", "Authorized"
    CAPTURED = "captured", "Captured"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    REFUNDED = "refunded", "Refunded"
    PARTIALLY_REFUNDED = "partially_refunded", "Partially Refunded"


class Payment(BaseModel):
    """Records a payment attempt and its result."""
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="payments")
    provider = models.CharField(max_length=50)
    provider_payment_id = models.CharField(max_length=255, db_index=True)
    provider_order_id = models.CharField(max_length=255, blank=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(max_length=30, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)

    # Full raw provider response for audit
    raw_response = models.JSONField(default=dict, blank=True)
    signature = models.TextField(blank=True)

    # Error info
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)

    # Refund tracking
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    refund_id = models.CharField(max_length=255, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["provider", "provider_payment_id"]),
            models.Index(fields=["order", "status"]),
        ]
        # Prevent duplicate payment records per provider
        unique_together = [("provider", "provider_payment_id")]

    def __str__(self):
        return f"{self.provider} payment {self.provider_payment_id} — {self.status}"

    @property
    def is_successful(self):
        return self.status == PaymentStatus.CAPTURED


class WebhookEvent(BaseModel):
    """Idempotency guard for incoming webhook events."""
    provider = models.CharField(max_length=50)
    event_id = models.CharField(max_length=255)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(blank=True)

    class Meta:
        verbose_name = "Webhook Event"
        unique_together = [("provider", "event_id")]
        indexes = [
            models.Index(fields=["provider", "event_id"]),
            models.Index(fields=["processed"]),
        ]

    def __str__(self):
        return f"{self.provider} / {self.event_type} / {self.event_id}"


class Invoice(BaseModel):
    """Invoice record generated after successful payment."""
    order = models.OneToOneField("orders.Order", on_delete=models.PROTECT, related_name="invoice")
    invoice_number = models.CharField(max_length=50, unique=True)
    storage_key = models.CharField(max_length=500, blank=True, help_text="PDF stored in object storage")
    issued_at = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="INR")
    sent_to_email = models.BooleanField(default=False)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return f"Invoice #{self.invoice_number}"

    def generate_invoice_number(self):
        from django.utils import timezone
        now = timezone.now()
        return f"INV-{now.year}{now.month:02d}-{str(self.id)[:8].upper()}"
