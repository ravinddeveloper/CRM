from django.urls import path

from apps.payments.views import webhook_view

app_name = "payments_api"

urlpatterns = [
    path("webhook/<str:provider>/", webhook_view, name="webhook"),
]
