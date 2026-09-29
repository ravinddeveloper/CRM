"""Dashboard redirect URL."""
from django.urls import path

from .views import dashboard_redirect

app_name = "dashboard"

urlpatterns = [
    path("", dashboard_redirect, name="redirect"),
]
