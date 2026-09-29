"""Coupons models."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel

User = get_user_model()


class DiscountType(models.TextChoices):
    PERCENTAGE = "percentage", "Percentage"
    FIXED = "fixed", "Fixed Amount"


class Coupon(BaseModel):
    """Discount coupon."""
    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices, default=DiscountType.PERCENTAGE)
    discount_value = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))]
    )
    max_discount_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Cap on maximum discount for percentage coupons."
    )
    minimum_order_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    # Applicable courses (empty = applies to all)
    applicable_courses = models.ManyToManyField("courses.Course", blank=True, related_name="coupons")

    # Validity
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    # Usage limits
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text="Total uses allowed. Null = unlimited.")
    max_uses_per_user = models.PositiveIntegerField(default=1)
    used_count = models.PositiveIntegerField(default=0)

    # Created by (admin/teacher)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_coupons"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["code", "is_active"])]

    def __str__(self):
        return f"Coupon: {self.code} ({self.discount_type} {self.discount_value})"

    @property
    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if now < self.valid_from or now > self.valid_until:
            return False
        if self.max_uses and self.used_count >= self.max_uses:
            return False
        return True

    def calculate_discount(self, subtotal: Decimal, course=None) -> Decimal:
        """Calculate the actual discount amount (server-side)."""
        if not self.is_valid:
            return Decimal("0.00")

        # Check course applicability
        if self.applicable_courses.exists() and course:
            if not self.applicable_courses.filter(pk=course.pk).exists():
                return Decimal("0.00")

        if subtotal < self.minimum_order_amount:
            return Decimal("0.00")

        if self.discount_type == DiscountType.PERCENTAGE:
            discount = (subtotal * self.discount_value / Decimal("100.00")).quantize(Decimal("0.01"))
            if self.max_discount_amount:
                discount = min(discount, self.max_discount_amount)
        else:
            discount = min(self.discount_value, subtotal)

        return discount


class CouponRedemption(BaseModel):
    """Records each time a coupon is used by a specific user."""
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="redemptions")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="coupon_redemptions")
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="coupon_redemptions")
    discount_applied = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = [("coupon", "order")]
        indexes = [models.Index(fields=["coupon", "user"])]

    def __str__(self):
        return f"{self.user.email} used {self.coupon.code}"
