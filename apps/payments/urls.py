from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("verify/", views.verify_payment_view, name="verify"),
    path("success/", views.payment_success_view, name="success"),
    path("failed/", views.payment_failed_view, name="failed"),
    path("webhook/<str:provider>/", views.webhook_view, name="webhook"),
    path("invoice/<uuid:order_id>/", views.download_invoice_view, name="download_invoice"),
]
