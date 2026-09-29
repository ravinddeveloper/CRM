"""Orders models - Order, OrderItem."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q

from apps.common.models import BaseModel

User = get_user_model()


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PAYMENT_INITIATED = "payment_initiated", "Payment Initiated"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    REFUNDED = "refunded", "Refunded"
    PARTIALLY_REFUNDED = "partially_refunded", "Partially Refunded"


class Order(BaseModel):
    """Represents a purchase transaction."""
    order_number = models.CharField(max_length=32, unique=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="orders")

    # Financial
    currency = models.CharField(max_length=3, default="INR")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2)

    # Status
    status = models.CharField(max_length=30, choices=OrderStatus.choices, default=OrderStatus.PENDING)

    # Coupon applied
    coupon = models.ForeignKey(
        "coupons.Coupon", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    coupon_code = models.CharField(max_length=50, blank=True)

    # Payment info
    payment_provider = models.CharField(max_length=50, blank=True)
    payment_transaction_id = models.CharField(max_length=255, blank=True, db_index=True)
    payment_provider_order_id = models.CharField(max_length=255, blank=True)

    # Billing info (snapshot at time of purchase)
    billing_name = models.CharField(max_length=255, blank=True)
    billing_email = models.EmailField(blank=True)
    billing_phone = models.CharField(max_length=20, blank=True)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["payment_transaction_id"]),
            models.Index(fields=["-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["payment_provider", "payment_transaction_id"],
                condition=~Q(payment_transaction_id=""),
                name="unique_payment_transaction",
            )
        ]

    def __str__(self):
        return f"Order #{self.order_number} — {self.user.email}"

    @property
    def is_completed(self):
        return self.status == OrderStatus.COMPLETED

    def generate_order_number(self):
        import random
        import string
        chars = string.ascii_uppercase + string.digits
        return "ORD-" + "".join(random.choices(chars, k=10))

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self.generate_order_number()
            # Ensure uniqueness
            while Order.objects.filter(order_number=self.order_number).exists():
                self.order_number = self.generate_order_number()
        super().save(*args, **kwargs)


class OrderItem(BaseModel):
    """Individual item (course) in an order."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    course = models.ForeignKey("courses.Course", on_delete=models.PROTECT, related_name="order_items")

    # Snapshot of price at time of purchase - crucial for historical integrity
    course_title = models.CharField(max_length=255)
    course_slug = models.SlugField(max_length=300)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    final_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = [("order", "course")]

    def __str__(self):
        return f"{self.course_title} in Order #{self.order.order_number}"

    @property
    def savings(self):
        return self.unit_price - self.final_price
