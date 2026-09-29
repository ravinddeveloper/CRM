"""Order service - builds orders, applies coupons, calculates totals."""
import logging
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from apps.coupons.models import Coupon, CouponRedemption
from apps.courses.models import Course

from .models import Order, OrderItem, OrderStatus

User = get_user_model()
logger = logging.getLogger("apps.orders")


class OrderService:
    """Creates and manages orders."""

    @staticmethod
    @transaction.atomic
    def create_order(
        user: User,
        courses: list[Course] | None = None,
        coupon_code: str | None = None,
        course_ids: list[str] | None = None,
    ) -> Order:
        """
        Build an order for one or more courses.
        ALL pricing is computed server-side. Never trust client-submitted prices.
        """
        if courses is None and course_ids is not None:
            courses = list(Course.objects.filter(id__in=course_ids))

        if not courses:
            raise ValueError("No courses provided.")

        # Validate courses are published
        for course in courses:
            if not course.is_published:
                raise ValueError(f"Course '{course.title}' is not available for purchase.")

        # Check for existing enrollments
        from apps.enrollments.models import Enrollment
        for course in courses:
            if Enrollment.objects.filter(user=user, course=course, status="active").exists():
                raise ValueError(f"You are already enrolled in '{course.title}'.")

        # Calculate line items (server-side pricing only)
        items_data = []
        subtotal = Decimal("0.00")
        for course in courses:
            price = course.effective_price  # uses discount_price if set, else price
            items_data.append({
                "course": course,
                "unit_price": price,
                "final_price": price,
            })
            subtotal += price

        # Apply coupon (server-side)
        discount_amount = Decimal("0.00")
        applied_coupon = None
        if coupon_code:
            try:
                coupon = Coupon.objects.get(code=coupon_code.upper())
                if not coupon.is_valid:
                    raise ValueError("Coupon is invalid or expired.")

                # Check per-user usage limit
                user_uses = CouponRedemption.objects.filter(coupon=coupon, user=user).count()
                if user_uses >= coupon.max_uses_per_user:
                    raise ValueError("You have already used this coupon the maximum number of times.")

                discount_amount = coupon.calculate_discount(subtotal)
                applied_coupon = coupon
            except Coupon.DoesNotExist:
                raise ValueError("Invalid coupon code.")

        # Calculate tax (server-side)
        taxable_amount = subtotal - discount_amount
        tax_rate = Decimal(str(getattr(settings, "TAX_RATE", "0.00")))
        tax_enabled = getattr(settings, "TAX_ENABLED", False)
        tax_amount = (taxable_amount * tax_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if tax_enabled else Decimal("0.00")

        total = taxable_amount + tax_amount

        # Create order
        order = Order.objects.create(
            user=user,
            currency=getattr(settings, "DEFAULT_CURRENCY", "INR"),
            subtotal=subtotal,
            discount_amount=discount_amount,
            tax_amount=tax_amount,
            total=total,
            status=OrderStatus.PENDING,
            coupon=applied_coupon,
            coupon_code=coupon_code.upper() if coupon_code else "",
            billing_name=user.full_name,
            billing_email=user.email,
        )

        # Create order items
        for item in items_data:
            OrderItem.objects.create(
                order=order,
                course=item["course"],
                course_title=item["course"].title,
                course_slug=item["course"].slug,
                unit_price=item["unit_price"],
                discount_amount=Decimal("0.00"),
                tax_amount=Decimal("0.00"),
                final_price=item["final_price"],
            )

        # Record coupon redemption
        if applied_coupon:
            CouponRedemption.objects.create(
                coupon=applied_coupon,
                user=user,
                order=order,
                discount_applied=discount_amount,
            )
            applied_coupon.used_count += 1
            applied_coupon.save(update_fields=["used_count"])

        logger.info("Order created: %s for user %s total %s", order.order_number, user.email, total)
        return order
