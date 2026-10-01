"""Orders views - checkout, order details, coupon application."""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.coupons.models import Coupon
from apps.courses.models import Course
from apps.enrollments.models import Enrollment
from apps.enrollments.services import EnrollmentService
from apps.orders.models import Order, OrderStatus
from apps.orders.services import OrderService
from apps.payments.services import PaymentService

logger = logging.getLogger("apps.orders")


@login_required(login_url="accounts:login")
def checkout_view(request):
    """
    Handle checkout review and summary page.
    Allows students to review their order, apply discount coupons,
    and proceed to payment gateway.
    """
    course_id = request.POST.get("course_id") or request.GET.get("course_id")
    coupon_code = request.POST.get("coupon_code") or request.GET.get("coupon_code", "").strip()

    if not course_id:
        messages.error(request, "Please select a course to checkout.")
        return redirect("marketplace:course_list")

    course = get_object_or_404(Course, id=course_id, status="published")

    # Check if user is the course mentor
    if request.user.is_teacher and course.teacher_id == request.user.id:
        messages.info(request, f"You are the instructor/mentor of '{course.title}'.")
        return redirect("teacher:sections", course_id=course.id)

    # Check if user is an administrator
    if request.user.is_admin or request.user.is_staff:
        messages.info(request, f"You have administrator access to '{course.title}'.")
        return redirect("admin_panel:course_curriculum", course_id=course.id)

    # Check if user is already enrolled
    if Enrollment.objects.filter(user=request.user, course=course, status="active").exists():
        messages.info(request, f"You are already enrolled in '{course.title}'.")
        return redirect("learn:course", course_slug=course.slug)

    coupon_error = None
    applied_code = coupon_code if coupon_code else None

    # Attempt to create/recalculate order with coupon
    try:
        order = OrderService.create_order(
            user=request.user,
            courses=[course],
            coupon_code=applied_code,
        )
    except ValueError as exc:
        # If coupon was invalid, create without coupon and show error on checkout page
        coupon_error = str(exc)
        order = OrderService.create_order(
            user=request.user,
            courses=[course],
            coupon_code=None,
        )
    except Exception as exc:
        logger.exception("Failed to create order: %s", exc)
        messages.error(request, "Could not initialize checkout. Please try again.")
        return redirect("marketplace:course_detail", slug=course.slug)

    # If action is to claim free course directly
    claim_free = request.POST.get("claim_free")
    if order.total <= 0 and (claim_free or request.method == "POST"):
        order.status = OrderStatus.COMPLETED
        order.save(update_fields=["status", "updated_at"])
        EnrollmentService.enroll_from_order(order)
        messages.success(request, f"Successfully enrolled in {course.title}!")
        return redirect(f"{reverse('payments:success')}?order_id={order.id}")

    # Prepare checkout payment provider data safely
    checkout_data = {}
    try:
        checkout_data = PaymentService.initiate_checkout(order)
    except Exception as exc:
        logger.warning("Payment initiation deferred for order %s: %s", order.order_number, exc)
        checkout_data = {
            "order_id": str(order.id),
            "order_number": order.order_number,
            "provider": "razorpay",
            "provider_order_id": f"order_{order.order_number}",
            "amount": str(order.total),
            "currency": order.currency,
            "key_id": "",
        }

    # Fetch available coupons for quick-apply suggestions
    available_coupons = Coupon.objects.filter(is_active=True).order_by("discount_value")[:3]

    context = {
        "order": order,
        "course": course,
        "checkout_data": checkout_data,
        "coupon_code": order.coupon_code or coupon_code,
        "coupon_error": coupon_error,
        "available_coupons": available_coupons,
    }
    return render(request, "payments/checkout.html", context)


@login_required(login_url="accounts:login")
def order_detail_view(request, id):
    """View details of a specific order."""
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "items__course"),
        id=id,
    )

    if order.user != request.user and not request.user.is_admin:
        raise Http404("Order not found.")

    invoice = getattr(order, "invoice", None)

    context = {
        "order": order,
        "invoice": invoice,
    }
    return render(request, "orders/detail.html", context)
