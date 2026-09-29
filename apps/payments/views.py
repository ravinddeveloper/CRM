"""Payment views - webhook, payment verification, success, failure, and invoices."""
import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.orders.models import Order, OrderStatus
from apps.payments.invoice_service import InvoiceService
from apps.payments.models import Invoice
from apps.payments.services import PaymentService

logger = logging.getLogger("payments")


@csrf_exempt
@require_http_methods(["POST"])
def webhook_view(request, provider: str):
    """
    Handle incoming webhooks from payment providers.
    Verifies signatures server-side and guarantees idempotency.
    """
    if provider == "razorpay":
        signature = request.META.get("HTTP_X_RAZORPAY_SIGNATURE", "")
    elif provider == "stripe":
        signature = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    else:
        return JsonResponse({"error": "Unsupported provider"}, status=400)

    if not signature:
        return JsonResponse({"error": "Missing signature"}, status=400)

    try:
        PaymentService.process_webhook(
            provider_name=provider,
            payload=request.body,
            signature=signature,
        )
        return JsonResponse({"status": "success"})
    except ValueError as exc:
        logger.warning("Webhook validation error for %s: %s", provider, exc)
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.error("Webhook processing error for %s: %s", provider, exc)
        return JsonResponse({"error": "Internal error"}, status=500)


@login_required(login_url="accounts:login")
@require_http_methods(["POST"])
def verify_payment_view(request):
    """
    Verify payment callback from frontend (Razorpay/Stripe modal completion).
    Server verifies provider signature before granting enrollment.
    """
    # Accept both Form data and JSON body
    if request.content_type == "application/json":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            data = {}
    else:
        data = request.POST

    order_id = data.get("order_id")
    if not order_id:
        return JsonResponse({"success": False, "error": "Order ID is required."}, status=400)

    order = get_object_or_404(Order, id=order_id, user=request.user)

    if order.status == OrderStatus.COMPLETED:
        # Idempotent response if already processed
        return JsonResponse({
            "success": True,
            "redirect_url": f"{reverse('payments:success')}?order_id={order.id}",
        })

    provider_payment_id = data.get("razorpay_payment_id") or data.get("payment_id") or data.get("stripe_payment_intent_id", "")
    provider_order_id = data.get("razorpay_order_id") or order.payment_provider_order_id
    signature = data.get("razorpay_signature") or data.get("signature", "")

    if not provider_payment_id:
        return JsonResponse({"success": False, "error": "Missing payment reference."}, status=400)

    try:
        PaymentService.verify_and_complete_payment(
            order=order,
            provider_payment_id=provider_payment_id,
            provider_order_id=provider_order_id,
            signature=signature,
        )
        return JsonResponse({
            "success": True,
            "redirect_url": f"{reverse('payments:success')}?order_id={order.id}",
        })
    except ValueError as exc:
        logger.warning("Payment verification rejected for order %s: %s", order.order_number, exc)
        return JsonResponse({"success": False, "error": str(exc)}, status=400)
    except Exception as exc:
        logger.exception("Unexpected error verifying payment for order %s: %s", order.order_number, exc)
        return JsonResponse({"success": False, "error": "Payment verification failed. Please contact support."}, status=500)


@login_required(login_url="accounts:login")
def payment_success_view(request):
    """Render payment success confirmation page."""
    order_id = request.GET.get("order_id")
    order = None
    if order_id:
        order = Order.objects.filter(id=order_id, user=request.user).prefetch_related("items", "items__course").first()

    return render(request, "payments/success.html", {"order": order})


@login_required(login_url="accounts:login")
def payment_failed_view(request):
    """Render payment failure notification page."""
    order_id = request.GET.get("order_id")
    order = None
    if order_id:
        order = Order.objects.filter(id=order_id, user=request.user).first()

    return render(request, "payments/failed.html", {"order": order})


@login_required(login_url="accounts:login")
def download_invoice_view(request, order_id):
    """Download signed PDF invoice for an order."""
    order = get_object_or_404(Order, id=order_id)
    if order.user != request.user and not request.user.is_admin:
        raise Http404("Invoice not found.")

    invoice = Invoice.objects.filter(order=order).first()
    if not invoice:
        # Generate on demand if missing
        invoice = Invoice.objects.create(
            order=order,
            user=order.user,
            total_amount=order.total,
            currency=order.currency,
        )
        InvoiceService.generate_pdf(invoice)
    elif not invoice.storage_key:
        InvoiceService.generate_pdf(invoice)

    download_url = InvoiceService.get_download_url(invoice)
    if download_url:
        return redirect(download_url)

    messages.info(request, "Invoice is currently being prepared. Please check back in a few moments.")
    return redirect("orders:detail", id=order.id)
